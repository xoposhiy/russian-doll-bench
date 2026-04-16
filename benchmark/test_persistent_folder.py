import io
import os
from pathlib import Path
import tarfile

import pytest

from benchmark.persistent_folder import PersistentFolder


def _write(path: Path, content: str) -> None:
    # Tests construct trees incrementally; keeping the helper tolerant of missing parents
    # makes each case focus on checkpoint behavior instead of directory bookkeeping.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _symlinks_supported(tmp_path: Path) -> bool:
    # Symlink availability is an environment property, especially on Windows (and locked-
    # down CI images?). Probing it explicitly keeps the behavior-based tests meaningful.
    source = tmp_path / "source.txt"
    link = tmp_path / "link.txt"
    source.write_text("x", encoding="utf-8")
    try:
        os.symlink(source.name, link)
    except (OSError, NotImplementedError):
        return False
    return True


def test_save_checkpoint_uses_content_addressable_archive(tmp_path: Path):
    root = tmp_path / "root"
    checkpoints = tmp_path / "checkpoints"
    root.mkdir()
    _write(root / "nested" / "data.txt", "alpha")

    folder = PersistentFolder(root, checkpoints)
    checkpoint1 = folder.save_checkpoint()
    checkpoint2 = folder.save_checkpoint()

    # Identical trees should collapse to the same checkpoint archive; otherwise the
    # advertised content-addressable storage would silently degrade into append-only blobs.
    assert checkpoint1 == checkpoint2


def test_restore_replaces_folder_contents_with_checkpoint(tmp_path: Path):
    root = tmp_path / "root"
    checkpoints = tmp_path / "checkpoints"
    root.mkdir()
    _write(root / "nested" / "data.txt", "before")
    _write(root / "keep.txt", "keep")

    folder = PersistentFolder(root, checkpoints)
    checkpoint = folder.save_checkpoint()

    # Restore is defined as "make the directory exactly match the checkpoint", so the
    # test mutates all three dimensions: changed content, removed file, and extra file.
    _write(root / "nested" / "data.txt", "after")
    _write(root / "new.txt", "extra")
    (root / "keep.txt").unlink()

    folder.restore(checkpoint)

    assert (root / "nested" / "data.txt").read_text(encoding="utf-8") == "before"
    assert (root / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert not (root / "new.txt").exists()


def test_restore_round_trips_internal_symlink(tmp_path: Path):
    if not _symlinks_supported(tmp_path):
        pytest.skip("symlinks are not available")

    root = tmp_path / "root"
    checkpoints = tmp_path / "checkpoints"
    root.mkdir()
    _write(root / "nested" / "target.txt", "inside-data")
    os.symlink("nested/target.txt", root / "linked-inside")
    _write(root / "inside.txt", "inside-data")

    folder = PersistentFolder(root, checkpoints)
    checkpoint = folder.save_checkpoint()

    link_path = root / "linked-inside"
    assert link_path.is_symlink()

    # The tree is mutated before restore so the test proves that normal in-tree symlinks
    # still round-trip even after tightening the escape checks.
    (root / "inside.txt").unlink()
    os.unlink(link_path)
    _write(root / "replacement.txt", "new")

    folder.restore(checkpoint)

    assert os.path.islink(root / "linked-inside")
    assert os.readlink(root / "linked-inside") == "nested/target.txt"
    assert (root / "nested" / "target.txt").read_text(encoding="utf-8") == "inside-data"
    assert not (root / "replacement.txt").exists()


def test_save_checkpoint_rejects_symlink_escaping_managed_folder(tmp_path: Path):
    if not _symlinks_supported(tmp_path):
        pytest.skip("symlinks are not available")

    root = tmp_path / "root"
    checkpoints = tmp_path / "checkpoints"
    root.mkdir()

    # The link itself lives under root, but recreating it would point outside the managed
    # tree. Checkpoint creation should reject it before an unusable archive is written.
    os.symlink("../outside", root / "linked-outside")

    folder = PersistentFolder(root, checkpoints)

    with pytest.raises(ValueError, match="symlink target escapes managed folder"):
        folder.save_checkpoint()


def test_init_rejects_checkpoints_dir_inside_root(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()

    # Restore clears the managed directory before extraction, so allowing checkpoints to
    # live inside that directory would make restore self-destructive by design.
    with pytest.raises(ValueError, match="outside the managed folder"):
        PersistentFolder(root, root / "checkpoints")


def test_restore_rejects_archive_with_parent_traversal(tmp_path: Path):
    root = tmp_path / "root"
    checkpoints = tmp_path / "checkpoints"
    root.mkdir()
    folder = PersistentFolder(root, checkpoints)

    archive_path = checkpoints / "bad.tar"
    with tarfile.open(archive_path, mode="w") as archive:
        # A malicious or hand-edited archive could try to escape the managed directory
        # even though extraction happens under root; validation must reject that shape.
        info = tarfile.TarInfo("../escape.txt")
        payload = b"bad"
        info.size = len(payload)
        archive.addfile(info, fileobj=io.BytesIO(payload))

    checkpoint = "bad"

    with pytest.raises(ValueError, match="parent traversal"):
        folder.restore(checkpoint)


def test_restore_rejects_archive_with_symlink_target_outside_root(tmp_path: Path):
    root = tmp_path / "root"
    checkpoints = tmp_path / "checkpoints"
    root.mkdir()
    folder = PersistentFolder(root, checkpoints)

    archive_path = checkpoints / "bad-symlink.tar"
    with tarfile.open(archive_path, mode="w") as archive:
        # Restore uses tar extraction under root, so any symlink target that escapes root
        # must be treated as a malformed checkpoint instead of delegated to tarfile.
        link = tarfile.TarInfo("link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../outside"
        archive.addfile(link)

    checkpoint = "bad-symlink"

    with pytest.raises(ValueError, match="symlink target escapes managed folder"):
        folder.restore(checkpoint)


def test_restore_rejects_archive_with_entries_under_symlink(tmp_path: Path):
    root = tmp_path / "root"
    checkpoints = tmp_path / "checkpoints"
    root.mkdir()
    folder = PersistentFolder(root, checkpoints)

    archive_path = checkpoints / "bad-link.tar"
    with tarfile.open(archive_path, mode="w") as archive:
        # Nested entries under a symlink are ambiguous and can be used to redirect writes
        # outside the managed tree, so the checkpoint reader rejects them entirely.
        link = tarfile.TarInfo("link")
        link.type = tarfile.SYMTYPE
        link.linkname = "target"
        archive.addfile(link)

        child = tarfile.TarInfo("link/file.txt")
        payload = b"bad"
        child.size = len(payload)
        archive.addfile(child, fileobj=io.BytesIO(payload))

    checkpoint = "bad-link"

    with pytest.raises(ValueError, match="nested under symlink"):
        folder.restore(checkpoint)

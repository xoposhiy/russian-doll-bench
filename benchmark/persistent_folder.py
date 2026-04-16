"""Folder checkpoints for quick saving and restoring content of the folder.

The checkpoint format is intentionally small: one content-addressed .tar file per
snapshot stored outside the managed folder. "tarfile" module already knows how to preserve
symlinks and POSIX ownership metadata, so leaning on it keeps the implementation pure
Python and cross-platform without inventing a second archive format to maintain.
"""

import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
import tempfile
from typing import Iterator


class PersistentFolder:
    """Save and restore the contents of a single directory.

    Checkpoints are stored as deterministic plain-tar archives outside ``root`` so that
    restore can safely replace the directory contents without deleting the checkpoints
    themselves. Plain tar is used instead of tar.gz because gzip normally embeds write-
    time metadata, which would break content-addressable storage for identical trees.

    Example:
        
        folder = PersistentFolder("working-directory")
        checkpoint_id = folder.save_checkpoint()
        ... make any modifications to the working directory ...
        folder.restore(checkpoint_id)
    """

    def __init__(self, root: str | Path, checkpoints_dir: str | Path | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.root = self.root.resolve()

        default_dir = self.root.parent / f".{self.root.name}.checkpoints"
        self.checkpoints_dir = Path(checkpoints_dir) if checkpoints_dir is not None else default_dir
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir = self.checkpoints_dir.resolve()

        if self._is_relative_to(self.checkpoints_dir, self.root):
            raise ValueError("checkpoints_dir must be outside the managed folder")

    def save_checkpoint(self) -> str:
        """Create or reuse a content-addressed tar archive for the current folder state."""
        fd, temp_name = tempfile.mkstemp(
            prefix="checkpoint-",
            suffix=".tar.tmp",
            dir=self.checkpoints_dir,
        )
        os.close(fd)
        temp_path = Path(temp_name)

        try:
            with tarfile.open(
                temp_path,
                mode="w",
                format=tarfile.PAX_FORMAT,
                dereference=False,
            ) as archive:
                for filesystem_path, arcname in self._iter_snapshot_entries():
                    self._ensure_supported_snapshot_entry(filesystem_path)
                    archive.add(
                        filesystem_path,
                        arcname=arcname,
                        recursive=False,
                        filter=self._normalize_tarinfo,
                    )

            checkpoint_id = self._sha256_file(temp_path)
            final_path = self.checkpoints_dir / f"{checkpoint_id}.tar"

            if final_path.exists():
                temp_path.unlink()
            else:
                temp_path.replace(final_path)

            return checkpoint_id
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    def restore(self, checkpoint: str) -> None:
        """Replace the managed folder contents with the given checkpoint."""
        archive_path = self._resolve_checkpoint_path(checkpoint)

        with tarfile.open(archive_path, mode="r") as archive:
            members = self._validated_members(archive)
            self._clear_root()
            archive.extractall(
                path=self.root,
                members=members,
                numeric_owner=(os.name != "nt"),
            )

    def get_checkpoint_path(self, checkpoint: str) -> Path:
        """Return the full path of the tar archive for the given checkpoint id."""
        return (self.checkpoints_dir / f"{checkpoint}.tar").resolve()

    def _iter_snapshot_entries(self) -> Iterator[tuple[Path, str]]:
        """Yield entries in a stable order suitable for content-addressable snapshots.

        Filesystem directory iteration order is platform-dependent. Sorting here keeps
        identical trees byte-for-byte identical in the generated tar archive.
        """
        yield from self._iter_directory(self.root, PurePosixPath())

    def _iter_directory(self, directory: Path, relative_path: PurePosixPath) -> Iterator[tuple[Path, str]]:
        with os.scandir(directory) as scan:
            entries = sorted(scan, key=lambda entry: entry.name)

        for entry in entries:
            entry_path = Path(entry.path)
            entry_relative = relative_path / entry.name
            yield entry_path, entry_relative.as_posix()

            # Manual recursion keeps symlinked directories archived as symlinks instead of
            # descending into them through tarfile's built-in recursive traversal.
            if entry.is_dir(follow_symlinks=False):
                yield from self._iter_directory(entry_path, entry_relative)

    @staticmethod
    def _normalize_tarinfo(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo:
        """Strip name-service data that does not affect restore semantics.

        ``tarfile`` can embed both numeric owners and the local username/group name. The
        numeric ids are the part relevant for restore; the textual names depend on the
        machine's account database and would otherwise perturb the content hash.
        """
        tarinfo.uname = ""
        tarinfo.gname = ""
        return tarinfo

    def _ensure_supported_snapshot_entry(self, path: Path) -> None:
        """Fail before archiving entries that cannot be restored portably.

        Benchmark sandboxes should be reproducible across Windows, macOS, and Linux.
        Device nodes and FIFOs are not, so snapshot creation rejects them instead of
        silently producing checkpoints with restore behavior that depends on the host OS.
        """
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            relative_path = path.relative_to(self.root).as_posix()
            self._assert_symlink_target_inside_root(
                link_path=relative_path,
                link_parent=os.path.dirname(relative_path),
                target=os.readlink(path),
            )
            return
        if stat.S_ISREG(mode) or stat.S_ISDIR(mode):
            return
        raise ValueError(f"unsupported filesystem entry for checkpointing: {path}")

    def _resolve_checkpoint_path(self, checkpoint: str) -> Path:
        candidate = self.get_checkpoint_path(checkpoint)
        if not self._is_relative_to(candidate, self.checkpoints_dir):
            raise ValueError("checkpoint must live inside checkpoints_dir")
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        return candidate

    def _validated_members(self, archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
        """Reject tar shapes that could escape ``root`` or change extraction semantics.

        ``tarfile`` faithfully trusts member names during extraction. Validation is done
        ahead of time so restore semantics stay limited to the managed directory even if a
        checkpoint file is tampered with or copied from elsewhere.
        """
        members = archive.getmembers()
        normalized: list[tarfile.TarInfo] = []
        seen_names: set[str] = set()
        symlink_names: set[str] = set()

        for member in members:
            if not (member.isfile() or member.isdir() or member.issym()):
                raise ValueError(f"unsupported tar member type for {member.name!r}")

            normalized_name = self._normalize_member_name(member.name)
            if normalized_name in seen_names:
                raise ValueError(f"duplicate tar member {normalized_name!r}")

            member.name = normalized_name
            normalized.append(member)
            seen_names.add(normalized_name)

            if member.issym():
                symlink_names.add(normalized_name)
                self._assert_symlink_target_inside_root(
                    link_path=normalized_name,
                    link_parent=PurePosixPath(normalized_name).parent.as_posix(),
                    target=member.linkname,
                )

        for member in normalized:
            member_path = PurePosixPath(member.name)
            for parent in member_path.parents:
                if parent == PurePosixPath("."):
                    break
                if parent.as_posix() in symlink_names:
                    raise ValueError(
                        f"tar member {member.name!r} is nested under symlink {parent.as_posix()!r}"
                    )

        return normalized

    @staticmethod
    def _normalize_member_name(name: str) -> str:
        path = PurePosixPath(name)
        if path.is_absolute():
            raise ValueError(f"absolute tar member paths are not allowed: {name!r}")
        if any(part == ".." for part in path.parts):
            raise ValueError(f"parent traversal is not allowed in tar members: {name!r}")

        cleaned_parts = [part for part in path.parts if part not in ("", ".")]
        if not cleaned_parts:
            raise ValueError("tar members must address a path inside the managed folder")
        return PurePosixPath(*cleaned_parts).as_posix()

    @staticmethod
    def _assert_symlink_target_inside_root(link_path: str, link_parent: str, target: str) -> None:
        """Reject links that would be recreated outside the managed folder.

        The check is lexical rather than filesystem-based so broken symlinks are still
        valid checkpoint content as long as they stay inside the managed tree.
        """
        drive, _ = os.path.splitdrive(target)
        if drive or os.path.isabs(target):
            raise ValueError(f"symlink target escapes managed folder: {link_path} -> {target}")

        candidate = os.path.normpath(os.path.join(link_parent, target))
        if candidate == ".." or candidate.startswith(f"..{os.sep}"):
            raise ValueError(f"symlink target escapes managed folder: {link_path} -> {target}")

    def _clear_root(self) -> None:
        """Remove the current tree before extracting the checkpoint.

        Restore is defined as making the folder exactly match the checkpoint. Clearing the
        tree first is simpler and less error-prone than trying to diff live state, and the
        explicit symlink check avoids following links out of the managed directory.
        """
        with os.scandir(self.root) as scan:
            entries = list(scan)

        for entry in entries:
            entry_path = Path(entry.path)
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(entry_path)
            else:
                entry_path.unlink()

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _is_relative_to(path: Path, parent: Path) -> bool:
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False

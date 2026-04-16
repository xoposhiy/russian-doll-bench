from __future__ import annotations

from pathlib import Path
import subprocess

from kaggle_benchmarks import envs as kb_envs

from benchmark.envs import (
    STDOUT_TRUNCATION_CHAR_LIMIT,
    LocalEnvironment,
    _format_truncated_stdout_notice,
    maybe_truncate_stdout,
)


def test_maybe_truncate_stdout_leaves_short_stdout_untouched(tmp_path: Path):
    stdout = "hello\nworld"

    truncated = maybe_truncate_stdout(stdout, working_dir=tmp_path)

    assert truncated == stdout
    assert list(tmp_path.iterdir()) == []


def test_maybe_truncate_stdout_writes_full_output_and_returns_notice(tmp_path: Path):
    stdout = ("abcde" * ((STDOUT_TRUNCATION_CHAR_LIMIT // 5) + 1))[: STDOUT_TRUNCATION_CHAR_LIMIT + 1]

    truncated = maybe_truncate_stdout(stdout, working_dir=tmp_path)

    files = list(tmp_path.iterdir())
    assert len(files) == 1
    saved_file = files[0]
    assert saved_file.read_text(encoding="utf-8") == stdout
    assert truncated.startswith(stdout[:STDOUT_TRUNCATION_CHAR_LIMIT])
    assert "stdout truncated" in truncated.lower()
    assert saved_file.name in truncated
    assert f"{len(stdout)} chars" in truncated
    assert f"{len(stdout.encode('utf-8'))} bytes" in truncated


def test_format_truncated_stdout_notice_counts_lines_and_bytes():
    stdout = "alpha\nbeta\n"

    notice = _format_truncated_stdout_notice(
        filename="run-stdout-test.txt",
        stdout=stdout,
        limit=5,
    )

    assert notice.startswith("alpha")
    assert "run-stdout-test.txt" in notice
    assert "11 chars" in notice
    assert "2 lines" in notice
    assert "11 bytes" in notice


def test_local_environment_truncates_subprocess_stdout(monkeypatch, tmp_path: Path):
    env = LocalEnvironment()
    env.temp_dir.cleanup()
    env.temp_dir = type("TempDir", (), {"name": str(tmp_path)})()

    def fake_run(*args, **kwargs):
        return type(
            "Completed",
            (),
            {
                "returncode": 0,
                "stdout": "x" * (STDOUT_TRUNCATION_CHAR_LIMIT + 50),
                "stderr": "",
            },
        )()

    monkeypatch.setattr("benchmark.envs.subprocess.run", fake_run)

    result = env.run("echo hi")

    assert isinstance(result, kb_envs.RunResult)
    assert result.exit_code == 0
    assert "stdout truncated" in result.stdout.lower()
    assert len(list(tmp_path.iterdir())) == 1


def test_local_environment_timeout_keeps_string_stdout(monkeypatch, tmp_path: Path):
    env = LocalEnvironment()
    env.temp_dir.cleanup()
    env.temp_dir = type("TempDir", (), {"name": str(tmp_path)})()

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="echo hi", timeout=10, output="partial stdout")

    monkeypatch.setattr("benchmark.envs.subprocess.run", fake_run)

    result = env.run("echo hi")

    assert result.exit_code == -1
    assert result.stdout == "partial stdout"
    assert "timed out after" in result.stderr

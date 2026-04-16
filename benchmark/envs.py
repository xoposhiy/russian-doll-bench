import shlex
import subprocess
import uuid
from pathlib import Path

from kaggle_benchmarks import envs


STDOUT_TRUNCATION_CHAR_LIMIT = 5000
TRUNCATED_STDOUT_FILENAME_PREFIX = "run-stdout-"


def _count_lines(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def _format_truncated_stdout_notice(*, filename: str, stdout: str, limit: int) -> str:
    preview = stdout[:limit]
    separator = "\n" if preview and not preview.endswith("\n") else ""
    return (
        f"{preview}{separator}"
        f"STDOUT truncated because it exceeded the {limit}-character limit. "
        f"Full output was saved to '{filename}'. "
        f"Stats: {len(stdout)} chars, {_count_lines(stdout)} lines, {len(stdout.encode('utf-8'))} bytes. "
        f"Inspect the file incrementally with grep, head, tail, sed, or similar tools instead of printing it whole."
    )


def maybe_truncate_stdout(stdout: str, *, working_dir: str | Path, limit: int = STDOUT_TRUNCATION_CHAR_LIMIT) -> str:
    if len(stdout) <= limit:
        return stdout

    working_path = Path(working_dir)
    working_path.mkdir(parents=True, exist_ok=True)
    filename = f"{TRUNCATED_STDOUT_FILENAME_PREFIX}{uuid.uuid4().hex}.txt"
    output_path = working_path / filename
    output_path.write_text(stdout, encoding="utf-8")
    return _format_truncated_stdout_notice(filename=filename, stdout=stdout, limit=limit)


def _coerce_subprocess_stdout(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


class LocalEnvironment(envs.LocalEnvironment):
    """
    Our drop-in replacement of kaggle_benchmarks.envs.LocalEnvironment to add a timeout to all runs.
    We also truncate stdout if it's too large.
    """

    TIMEOUT_SECONDS = 10

    def run(
            self, command: str | list[str], input: str | None = None
    ) -> envs.RunResult:
        """Runs a shell command in the temporary directory."""
        try:
            result = subprocess.run(
                command,
                shell=isinstance(command, str),
                input=input,
                timeout=self.TIMEOUT_SECONDS,
                cwd=self.temp_dir.name,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _coerce_subprocess_stdout(exc.stdout)

            return envs.RunResult(
                exit_code=-1,
                stdout=maybe_truncate_stdout(stdout, working_dir=self.temp_dir.name),
                stderr=f"ERROR: execution timed out after {self.TIMEOUT_SECONDS} seconds. "
                       f"Only {self.TIMEOUT_SECONDS} seconds are allowed.",
            )

        return envs.RunResult(
            exit_code=result.returncode,
            stdout=maybe_truncate_stdout(result.stdout, working_dir=self.temp_dir.name),
            stderr=result.stderr,
        )


class DockerEnvironment(envs.DockerEnvironment):
    """
    Our drop-in replacement of kaggle_benchmarks.envs.DockerEnvironment to add a timeout to all runs.
    We also truncate stdout if it's too large.
    """

    TIMEOUT_SECONDS = 30

    def run(
        self, command: str | list[str], input: str | None = None
    ) -> envs.RunResult:
        """Runs a command in the container."""
        if self.container is None:
            raise RuntimeError("Container was not started")

        if input is not None:
            raise NotImplementedError("input is not supported")

        if not isinstance(command, str):
            command = shlex.join(command)

        result = self.container.exec_run(
            ["timeout", str(self.TIMEOUT_SECONDS), "sh", "-c", command], demux=True, workdir=self.working_dir,
        )
        return envs.RunResult(
            result.exit_code,
            stdout=maybe_truncate_stdout((result.output[0] or b"").decode(), working_dir=self.directory),
            stderr=(result.output[1] or b"").decode(),
        )

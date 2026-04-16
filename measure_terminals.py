#!/usr/bin/env python
"""
Measure per-terminal benchmark usage for one or more models.

The script supports two modes:

- `solve`: run a single `terminal_chain` benchmark for each terminal spec.
- `adaptive-learning`: run `adaptive_learning` with a generator constrained to a
  single terminal spec and measure whether the model can build a reusable
  `main.py` for that terminal family.

It writes a CSV report and prints the same data as a human-readable table.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import docker.types

from run_benchmark import _configure_kaggle_client, _prepare_model_env, make_llm
from server.terminal_spec import normalize_terminal_spec, DEFAULT_TERMINAL_CLASSES
from benchmark.task_generator import TaskSpecGenerator


@dataclass(frozen=True)
class TerminalMeasurement:
    started_at: str
    model: str
    mode: str
    terminal: str
    solved: bool
    iterations: int
    output_tokens: int
    input_tokens: int
    input_uncached_tokens: int


MEASUREMENT_MODES = ("solve", "adaptive-learning")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run single-terminal benchmark tasks and report token usage."
    )
    parser.add_argument(
        "--model",
        required=True,
        help="Model ID or comma-separated model IDs (for example gemini-2.0-flash,gpt-5-mini).",
    )
    parser.add_argument(
        "--terminals",
        help=(
            "Comma-separated terminal specs to run. Defaults to all single wrapper "
            "terminals, each with an implicit nested main terminal."
        ),
    )
    parser.add_argument(
        "--include-main",
        action="store_true",
        help="Also run the standalone main terminal as a baseline row.",
    )
    parser.add_argument(
        "--mode",
        choices=MEASUREMENT_MODES,
        default="solve",
        help=(
            "Measurement mode: `solve` runs one terminal_chain attempt; "
            "`adaptive-learning` runs adaptive_learning for the terminal spec and "
            "measures whether the model can build a reusable main.py."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for terminal initialization (default: 42).",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=100,
        help="Maximum number of agent-loop iterations per attempt (default: 100).",
    )
    parser.add_argument(
        "--adaptive-max-attempts",
        type=int,
        default=5,
        help="Maximum adaptive_learning attempts per generator before failing (default: 5).",
    )
    parser.add_argument(
        "--adaptive-task-count",
        type=int,
        default=50,
        help="Number of generated tasks per terminal in adaptive-learning mode (default: 50).",
    )
    parser.add_argument(
        "--csv",
        help=(
            "Output CSV path. Defaults to logs/measure-terminals/<mode>.csv and "
            "appends new rows."
        ),
    )
    return parser.parse_args()


def default_terminal_specs(*, include_main: bool = False) -> list[str]:
    excluded = {"dummy"}
    terminals = sorted(
        name
        for name in DEFAULT_TERMINAL_CLASSES
        if name not in excluded and (include_main or name != "main")
    )
    if include_main and "main" in terminals:
        terminals.remove("main")
        terminals.insert(0, "main")
    return terminals


def parse_terminal_specs(raw_specs: str | None, *, include_main: bool) -> list[str]:
    if not raw_specs:
        return default_terminal_specs(include_main=include_main)

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_spec in raw_specs.split(","):
        spec = normalize_terminal_spec(raw_spec.strip())
        if spec not in seen:
            normalized.append(spec)
            seen.add(spec)
    return normalized


def _first_int(metrics: dict[str, int], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = metrics.get(key)
        if isinstance(value, int):
            return value
    return None


def _effective_input_tokens(token_metrics: dict[str, int]) -> int:
    return _first_int(
        token_metrics,
        (
            "input_tokens",
            "inputTokens",
            "prompt_token_count",
        ),
    ) or 0


def _effective_cached_input_tokens(token_metrics: dict[str, int]) -> int:
    return _first_int(
        token_metrics,
        (
            "cached_content_token_count",
            "cached_input_tokens",
            "cache_read_input_tokens",
        ),
    ) or 0


def _effective_uncached_input_tokens(token_metrics: dict[str, int]) -> int:
    uncached = _first_int(
        token_metrics,
        (
            "uncached_input_tokens",
            "billable_input_tokens",
        ),
    )
    if uncached is not None:
        return uncached
    return max(_effective_input_tokens(token_metrics) - _effective_cached_input_tokens(token_metrics), 0)


def _effective_output_tokens(token_metrics: dict[str, int]) -> int:
    output_tokens = _first_int(
        token_metrics,
        (
            "output_tokens",
            "outputTokens",
        ),
    )
    if output_tokens is not None:
        return output_tokens

    candidates = _first_int(token_metrics, ("candidates_token_count",)) or 0
    thoughts = _first_int(token_metrics, ("thoughts_token_count", "reasoning_token_count")) or 0
    tool_calls = _first_int(
        token_metrics,
        (
            "tool_use_prompt_token_count",
            "tool_call_token_count",
        ),
    ) or 0
    return candidates + thoughts + tool_calls


def parse_models(raw_models: str) -> list[str]:
    models: list[str] = []
    seen: set[str] = set()
    for raw_model in raw_models.split(","):
        model = raw_model.strip()
        if not model:
            continue
        if model not in seen:
            models.append(model)
            seen.add(model)
    if not models:
        raise ValueError("At least one model must be provided.")
    return models


def _default_csv_path(mode: str) -> Path:
    return Path("logs") / "measure-terminals" / f"{_sanitize_filename(mode)}.csv"


def _build_run_log_dir(csv_path: Path) -> Path:
    return csv_path.parent / csv_path.stem


def _sanitize_filename(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)


def format_measurements_table(rows: list[TerminalMeasurement]) -> str:
    headers = (
        ("Model", "model"),
        ("Mode", "mode"),
        ("Terminal", "terminal"),
        ("Solved", "solved"),
        ("Iterations", "iterations"),
        ("Output tokens", "output_tokens"),
        ("Input tokens", "input_tokens"),
        ("Input uncached tokens", "input_uncached_tokens"),
    )
    widths = []
    for title, field_name in headers:
        width = len(title)
        for row in rows:
            width = max(width, len(str(getattr(row, field_name))))
        widths.append(width)

    def format_row(values: list[str]) -> str:
        return " | ".join(value.ljust(width) for value, width in zip(values, widths, strict=True))

    header_line = format_row([title for title, _ in headers])
    separator_line = "-+-".join("-" * width for width in widths)
    body_lines = [
        format_row([str(getattr(row, field_name)) for _, field_name in headers])
        for row in rows
    ]
    return "\n".join([header_line, separator_line, *body_lines])


def _measurement_table_layout() -> tuple[tuple[str, str, int], ...]:
    return (
        ("Model", "model", 22),
        ("Mode", "mode", 17),
        ("Terminal", "terminal", 18),
        ("Solved", "solved", 8),
        ("Iterations", "iterations", 10),
        ("Output tokens", "output_tokens", 14),
        ("Input tokens", "input_tokens", 13),
        ("Input uncached", "input_uncached_tokens", 15),
    )


def print_measurements_table_header() -> None:
    layout = _measurement_table_layout()
    header = " | ".join(title.ljust(width) for title, _, width in layout)
    separator = "-+-".join("-" * width for _, _, width in layout)
    print(header)
    print(separator)


def print_measurement_table_row(row: TerminalMeasurement) -> None:
    layout = _measurement_table_layout()
    values = [str(getattr(row, field_name)).ljust(width) for _, field_name, width in layout]
    print(" | ".join(values), flush=True)


def print_progress_status(index: int, total: int, model: str, terminal_spec: str) -> None:
    message = f"[{index}/{total}] Measuring model={model} terminal={terminal_spec}..."
    print(f"\r{message}", end="", file=sys.stderr, flush=True)


def clear_progress_status() -> None:
    print("\r" + (" " * 120) + "\r", end="", file=sys.stderr, flush=True)


def write_csv_report(path: Path, rows: list[TerminalMeasurement]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "started_at",
                "model",
                "mode",
                "terminal",
                "solved",
                "iterations",
                "output_tokens",
                "input_tokens",
                "input_uncached_tokens",
            ],
        )
        if not file_exists or path.stat().st_size == 0:
            writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def append_csv_row(path: Path, row: TerminalMeasurement) -> None:
    write_csv_report(path, [row])


def _aggregate_jsonl_metrics(log_file: Path) -> tuple[int, dict[str, int]]:
    iterations = 0
    token_metrics: dict[str, int] = {}
    if not log_file.exists():
        return iterations, token_metrics

    with log_file.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        for raw_line in fh:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            if event.get("event_type") == "run_summary":
                event_iterations = event.get("iterations")
                if isinstance(event_iterations, int):
                    iterations += event_iterations

            if event.get("event_type") != "model_response":
                continue
            usage = event.get("usage_metadata")
            if not isinstance(usage, dict):
                continue
            for key, value in usage.items():
                if isinstance(value, int):
                    token_metrics[key] = token_metrics.get(key, 0) + value

    return iterations, token_metrics


def run_single_terminal_measurement(
    *,
    llm,
    model: str,
    mode: str,
    started_at: str,
    terminal_spec: str,
    seed: int,
    max_steps: int,
    adaptive_max_attempts: int,
    adaptive_task_count: int,
    log_dir: Path,
) -> TerminalMeasurement:
    from benchmark import tasks, legacy_tasks
    from benchmark.envs import DockerEnvironment
    from benchmark.infrastructure import (
        VirtualFileSystem,
        create_timestamped_temp_folder,
        get_run_logger,
    )
    from benchmark.telemetry import set_log_file
    from kaggle_benchmarks import envs

    log_suffix = (
        f"{_sanitize_filename(started_at)}-"
        f"{_sanitize_filename(model)}-"
        f"{_sanitize_filename(mode)}-"
        f"{_sanitize_filename(terminal_spec)}.jsonl"
    )
    log_file = log_dir / log_suffix
    set_log_file(str(log_file))
    _configure_kaggle_client(str(log_dir))

    working_directory = create_timestamped_temp_folder()
    VirtualFileSystem.override_root(working_directory)

    docker_env_configuration = DockerEnvironment(
        image="cimg/python:3.14",
        extra_hosts={"host.docker.internal": "host-gateway"},
    )
    docker_env_configuration.mounts = [
        docker.types.Mount("/tmp", str(working_directory), type="bind")
    ]

    try:
        with docker_env_configuration as docker_env:
            envs.current = docker_env
            docker_env.run(["pip", "install", "requests"])
            tasks.TaskEnvironment.override_server_host("host.docker.internal")
            if mode == "solve":
                run = legacy_tasks.terminal_chain.run(
                    llm,
                    terminal_spec=terminal_spec,
                    seed=seed,
                    max_steps=max_steps,
                )
            elif mode == "adaptive-learning":
                run = tasks.adaptive_learning.run(
                    llm,
                    generators=[
                        TaskSpecGenerator(
                            terminal_spec,
                            tasks_count=adaptive_task_count,
                            base_seed=seed,
                        )
                    ],
                    max_attempts_per_generator=adaptive_max_attempts,
                )
            else:
                raise ValueError(f"Unsupported measurement mode: {mode}")
    finally:
        VirtualFileSystem.override_root(None)

    aggregated_iterations, token_metrics = _aggregate_jsonl_metrics(log_file)
    measurement = TerminalMeasurement(
        started_at=started_at,
        model=model,
        mode=mode,
        terminal=terminal_spec,
        solved=bool(getattr(run, "passed", False)),
        iterations=aggregated_iterations,
        output_tokens=_effective_output_tokens(token_metrics),
        input_tokens=_effective_input_tokens(token_metrics),
        input_uncached_tokens=_effective_uncached_input_tokens(token_metrics),
    )
    get_run_logger().set_iteration(None)
    return measurement


def main() -> None:
    args = parse_args()
    models = parse_models(args.model)
    terminal_specs = parse_terminal_specs(args.terminals, include_main=args.include_main)
    csv_path = Path(args.csv) if args.csv else _default_csv_path(args.mode)
    run_log_dir = _build_run_log_dir(csv_path)

    rows: list[TerminalMeasurement] = []
    print_measurements_table_header()
    total_runs = len(models) * len(terminal_specs)
    run_index = 0
    for model in models:
        _prepare_model_env(model)
        llm = make_llm(model)
        started_at = datetime.now().isoformat(timespec="seconds")
        for terminal_spec in terminal_specs:
            run_index += 1
            print_progress_status(run_index, total_runs, model, terminal_spec)
            row = run_single_terminal_measurement(
                    llm=llm,
                    model=model,
                    mode=args.mode,
                    started_at=started_at,
                    terminal_spec=terminal_spec,
                    seed=args.seed,
                    max_steps=args.max_steps,
                    adaptive_max_attempts=args.adaptive_max_attempts,
                    adaptive_task_count=args.adaptive_task_count,
                    log_dir=run_log_dir,
                )
            clear_progress_status()
            rows.append(row)
            append_csv_row(csv_path, row)
            print_measurement_table_row(row)

    from benchmark.infrastructure import get_run_logger

    get_run_logger().close()

    print()
    print(format_measurements_table(rows))
    print()
    print(f"CSV report: {csv_path.resolve()} (appended)")
    print(f"Run logs  : {run_log_dir.resolve()}")


if __name__ == "__main__":
    main()

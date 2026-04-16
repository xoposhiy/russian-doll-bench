#!/usr/bin/env python
"""
Run the Russian Doll benchmark against a specific model.

The script runs one of the Kaggle benchmark tasks directly, which spins up the
HTTP terminal server internally and emits Kaggle `.run.json` artifacts.

Usage:
  python run_benchmark.py --model <model_id> --terminal <spec> [options]

Terminal spec examples:
  main
  sys32
  maze
  sys32-maze
  sys32(42)-maze(12121)-sys32(52)

Examples:
  python run_benchmark.py --model gemini-2.0-flash --task terminal_chain --terminal sys32
  python run_benchmark.py --model gemini-2.5-pro --task terminal_chain --terminal maze
  python run_benchmark.py --model gemini-2.5-pro --task terminal_chain --terminal strings(seed=7)
  python run_benchmark.py --model gemini-2.5-pro --task terminal_chain --terminal sys32-maze
  python run_benchmark.py --model gemini-2.5-pro --task terminal_chain --terminal sys32(42)-maze(12121)-sys32(52)
  python run_benchmark.py --model gemini-2.5-pro --task terminal_chain --terminal strings --verbose

  python run_benchmark.py --model gemini-2.5-pro --task infrastructure_evolution --training sys32(10),sys32(20) --validating sys32(10)

  python run_benchmark.py --model gemini-2.5-pro --task adaptive_learning --generators sys32,sys32-sys32,sys32|hash-sys32
"""

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import docker.types
from dotenv import load_dotenv

from benchmark.task_generator import TaskSpecGenerator
from server.terminal_spec import TerminalBySpecBuilder

_REPO_ROOT = Path(__file__).resolve().parent
_DOTENV_PATH = _REPO_ROOT / ".env"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a single Russian Doll benchmark task."
    )
    parser.add_argument(
        "--model",
        required=True,
        help="Model ID (e.g. gemini-2.0-flash, gpt-5-mini)",
    )
    parser.add_argument(
        "--task",
        required=True,
        help="Task name (e.g. terminal_chain, infrastructure_evolution)",
    )
    parser.add_argument(
        "--terminal",
        required=False,
        help="Terminal chain spec for the terminal_chain task, for example sys32-maze-sys32 or main",
    )
    parser.add_argument(
        "--training",
        required=False,
        help="Training terminal chain specs (separated by command) for the infrastructure_evolution task, for example --training sys32(10),sys32(20)",
    )
    parser.add_argument(
        "--validating",
        required=False,
        help="Validating terminal chain specs (separated by command) for the infrastructure_evolution task, for example --validating sys32(10),sys32(20)",
    )
    parser.add_argument(
        "--generators",
        required=False,
        help="Terminal generators (separated by command) for the adaptive_learning task, for example --generators sys32,sys32-sys32,sys32|hash-sys32",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for terminal initialisation (default: 42)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print step-by-step log to stderr",
    )
    parser.add_argument(
        "--log-file",
        help="Write structured JSONL telemetry to this file (default: logs/<timestamp>-<model>-<terminal>.jsonl)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=100,
        help="Maximum number of agent-loop iterations (default: 100)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# LLM helper
# ---------------------------------------------------------------------------

def _proxy_supports_genai() -> bool:
    value = os.environ.get("MODEL_PROXY_GENAI_SUPPORT", "TRUE").strip().upper()
    return value not in {"0", "FALSE", "NO", "OFF"}


def make_llm(model: str):
    normalized = model.removeprefix("google/")

    from kaggle_benchmarks.kaggle import load_model

    proxy_url = os.environ.get("MODEL_PROXY_URL", "")
    proxy_key = os.environ.get("MODEL_PROXY_API_KEY", "")
    if not proxy_url or not proxy_key:
        sys.exit(
            "ERROR: MODEL_PROXY_URL and MODEL_PROXY_API_KEY are required."
        )
    api = "genai" if normalized.startswith("gemini-") and _proxy_supports_genai() else "openai"
    return load_model(model_name=model, api=api)


def _load_runtime_env() -> None:
    if not _DOTENV_PATH.exists():
        sys.exit(f"ERROR: .env file not found: {_DOTENV_PATH}")
    load_dotenv(dotenv_path=_DOTENV_PATH, override=True)


def _prepare_model_env(model: str) -> None:
    """
    Load runtime configuration from .env and validate the proxy settings.
    """
    _load_runtime_env()

    os.environ["LLM_DEFAULT"] = model

    proxy_url = os.environ.get("MODEL_PROXY_URL", "")
    proxy_key = os.environ.get("MODEL_PROXY_API_KEY", "")
    if not proxy_url or not proxy_key:
        sys.exit(
            "ERROR: .env must define MODEL_PROXY_URL and MODEL_PROXY_API_KEY."
        )


def _default_log_file(model: str, terminal: str) -> str:
    from benchmark.infrastructure import get_log_filename
    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_filename = get_log_filename(terminal, model)
    return str(logs_dir / log_filename)


def _configure_kaggle_client(directory: str):
    import kaggle_benchmarks as kbench
    from kaggle_benchmarks.kaggle.client import KaggleClient

    client = KaggleClient(directory=directory)
    kbench.client = client
    return client


def _collect_run_token_metrics(run_file: Path) -> dict[str, int]:
    if not run_file.exists():
        return {}

    data = json.loads(run_file.read_text(encoding="utf-8"))
    totals: Counter[str] = Counter()
    for conversation in data.get("conversations", []):
        for request in conversation.get("requests", []):
            for key, value in request.get("metrics", {}).items():
                if isinstance(value, int):
                    totals[key] += value
    return dict(totals)


def _collect_jsonl_token_metrics(log_file: Path) -> dict[str, int]:
    if not log_file.exists():
        return {}

    totals: Counter[str] = Counter()
    with log_file.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        for raw_line in fh:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if event.get("event_type") != "model_response":
                continue
            usage = event.get("usage_metadata") or {}
            if not isinstance(usage, dict):
                continue
            for key, value in usage.items():
                if isinstance(value, int):
                    totals[key] += value
    return dict(totals)


def _collect_latest_benchmark_events(log_file: Path) -> tuple[dict, dict]:
    if not log_file.exists():
        return {}, {}

    latest_run_summary: dict = {}
    latest_validation_summary: dict = {}
    with log_file.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        for raw_line in fh:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            event_type = event.get("event_type")
            if event_type == "run_summary":
                latest_run_summary = event
            elif event_type == "validation_summary":
                latest_validation_summary = event
    return latest_run_summary, latest_validation_summary



def _effective_total_tokens(token_metrics: dict[str, int]) -> int:
    if not token_metrics:
        return 0
    for total_key in ("total_token_count", "total_tokens", "totalTokens"):
        if isinstance(token_metrics.get(total_key), int):
            return token_metrics[total_key]
    total = 0
    for key in (
        "inputTokens",
        "outputTokens",
        "input_tokens",
        "output_tokens",
        "prompt_token_count",
        "candidates_token_count",
    ):
        value = token_metrics.get(key)
        if isinstance(value, int):
            total += value
    return total


def _format_task_outcome(
    *,
    task_name: str,
    run_result,
    latest_run_summary: dict,
    latest_validation_summary: dict,
) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []

    score = max_score = None
    if isinstance(run_result, tuple) and len(run_result) == 2:
        score, max_score = run_result

    if task_name == "terminal_chain":
        if score is not None and max_score is not None:
            lines.append(("Activation", f"{score} / {max_score}"))
        activated = latest_run_summary.get("activated_terminals_count")
        total_terminals = latest_run_summary.get("total_terminals")
        if activated is not None and total_terminals is not None:
            lines.append(("Terminals", f"{activated} / {total_terminals} online"))
        done = latest_run_summary.get("done")
        if done is not None:
            lines.append(("Completed", "yes" if done else "no"))
        return lines

    if task_name == "infrastructure_evolution":
        passed = latest_validation_summary.get("number_of_passed_validating_terminals")
        total = latest_validation_summary.get("total")
        if passed is not None and total is not None:
            lines.append(("Validation", f"{passed} / {total} terminals passed"))
        if score is not None and max_score:
            if score > 0:
                training_round = max_score - score + 1
                lines.append(("Outcome", f"full validation passed after training round {training_round} / {max_score}"))
            else:
                lines.append(("Outcome", f"full validation never passed across {max_score} training rounds"))
        return lines

    if score is not None and max_score is not None:
        lines.append(("Result", f"{score} / {max_score}"))
    return lines


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    _prepare_model_env(args.model)

    # These imports should go strictly after _prepare_model_env() call
    from benchmark import tasks, legacy_tasks
    from benchmark.envs import DockerEnvironment
    from benchmark.infrastructure import (
        get_run_logger, VirtualFileSystem, create_timestamped_temp_folder,
        get_last_agent_error
    )
    from benchmark.telemetry import set_log_file, enable_logging, get_last_run_metrics
    from kaggle_benchmarks import envs
    from kaggle_benchmarks.kaggle.serialization import generate_run_filename

    log_file = args.log_file or _default_log_file(args.model, args.task)
    set_log_file(log_file)
    enable_logging()

    logs_dir = str(Path(log_file).resolve().parent)
    _configure_kaggle_client(logs_dir)

    if args.task == "terminal_chain":
        task = legacy_tasks.terminal_chain
    elif args.task == "infrastructure_evolution":
        task = legacy_tasks.infrastructure_evolution
    elif args.task == "adaptive_learning":
        task = tasks.advanced_adaptive_learning
    else:
        raise ValueError(f"Unknown task: {args.task}. Available tasks: terminal_chain, infrastructure_evolution, adaptive_learning")

    llm = make_llm(args.model)

    working_directory = create_timestamped_temp_folder()
    VirtualFileSystem.override_root(working_directory)

    print(f"Model      : {args.model}")
    print(f"Task       : {task.name}")
    print(f"Seed       : {args.seed}")
    print(f"Log        : {log_file}")
    print(f"Artifacts  : {logs_dir}")
    print(f"Working dir: {working_directory.as_posix()}")
    print("-" * 40)

    print("[tool-mode] Starting a Docker container to run the commands...")

    # For local runs, we use a Docker environment to isolate LLM's tools from the local machine.
    # On Kaggle, all code is already running inside an isolated environment, so we use a default LocalEnvironment there.
    docker_env_configuration = DockerEnvironment(
        image="cimg/python:3.14",  # a CircleCI image having both modern Python and curl
        extra_hosts={"host.docker.internal": "host-gateway"}
    )
    # Workarounding a bug in kaggle_benchmarks
    # (they forgot type="bind" and swapped target and source for the working dir)
    docker_env_configuration.mounts = [
        docker.types.Mount("/tmp", str(working_directory), type="bind")
    ]
    with docker_env_configuration as docker_env:
        # Use Docker environment as a default one
        envs.current = docker_env

        # Install requests inside the Docker container because it's useful to the LLM
        docker_env.run(["pip", "install", "requests"])

        # Server is running outside the Docker container, so we need to change the way
        # how LLM is trying to reach the server.
        tasks.TaskEnvironment.override_server_host("host.docker.internal")

        start = time.time()
        if args.task == "terminal_chain":
            try:
                terminal_spec = TerminalBySpecBuilder().normalize_terminal_spec(args.terminal)
            except ValueError as exc:
                sys.exit(f"ERROR: invalid terminal spec: {exc}")

            run = task.run(llm, terminal_spec=terminal_spec, seed=args.seed, max_steps=args.max_steps)
        elif args.task == "infrastructure_evolution":
            run = task.run(
                llm,
                training_terminals=args.training.split(",") if args.training else None,
                validating_terminals=args.validating.split(",") if args.validating else None,
            )
        elif args.task == "adaptive_learning":
            run = tasks.run_adaptive_learning(llm)
        else:
            raise ValueError(f"Unknown task: {args.task}. Available tasks: terminal_chain, infrastructure_evolution, adaptive_learning")

        elapsed = time.time() - start

    agent_error = get_last_agent_error()
    run_file = Path(logs_dir) / generate_run_filename(task.name, run.cache_id)
    token_metrics = _collect_run_token_metrics(run_file)
    if not token_metrics:
        token_metrics = _collect_jsonl_token_metrics(Path(log_file))
    runtime_metrics = get_last_run_metrics()
    latest_run_summary, latest_validation_summary = _collect_latest_benchmark_events(Path(log_file))
    get_run_logger().close()

    print("\nResult")
    print(f"Status     : {'passed' if run.passed else 'failed'}")
    for label, value in _format_task_outcome(
        task_name=task.name,
        run_result=run.result,
        latest_run_summary=latest_run_summary,
        latest_validation_summary=latest_validation_summary,
    ):
        print(f"{label:<11}: {value}")
    print(f"Time       : {elapsed:.1f}s")
    if runtime_metrics is not None:
        print(f"Iterations : {runtime_metrics.iterations}")
        if runtime_metrics.created_files:
            print(f"Files      : {len(runtime_metrics.created_files)} created")
    total_tokens = _effective_total_tokens(token_metrics)
    if total_tokens:
        print(f"Tokens     : {total_tokens}")

    if run.error_message:
        print(f"Run error  : {run.error_message}")
    if agent_error:
        print(f"Agent error: {agent_error}")

    print(f"Run file   : {run_file}")
    print(f"JSONL log  : {Path(log_file).resolve()}")
    print(f"Working dir: {working_directory.resolve()}")


if __name__ == "__main__":
    main()

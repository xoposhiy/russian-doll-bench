"""
Structured run telemetry for benchmark and server events.
"""

from __future__ import annotations

import json
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kaggle_benchmarks import Usage


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _shorten(value: Any, limit: int = 120) -> str:
    text = str(value).replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _json_safe(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if hasattr(value, "__dict__"):
            return {
                key: _json_safe(val)
                for key, val in value.__dict__.items()
                if not key.startswith("_")
            }
        return str(value)


def _render_console_event(event: dict[str, Any]) -> str:
    iteration = event.get("iteration")
    prefix = f"[{iteration}] " if iteration is not None else ""
    event_type = event["event_type"]

    if event_type == "run_start":
        return (
            f"{prefix}run_start model={event.get('model')} terminal={event.get('terminal_spec')} "
            f"seed={event.get('seed')} max_steps={event.get('max_steps')} vfs_root={event.get('vfs_root')}"
        )
    if event_type == "run_end":
        return (
            f"{prefix}run_end score={event.get('score')}/{event.get('max_score')} "
            f"done={event.get('done')}"
        )
    if event_type == "run_summary":
        return (
            f"{prefix}summary iterations={event.get('iterations')} created_files={event.get('created_files_count')} "
            f"tokens={event.get('total_tokens', 0)}"
        )
    if event_type == "terminal_input":
        return f"{prefix}terminal {event.get('terminal_id')} <= {_shorten(event.get('payload', ''))}"
    if event_type == "terminal_output":
        return f"{prefix}terminal {event.get('terminal_id')} => {_shorten(event.get('payload', ''))}"
    if event_type == "terminal_online":
        return f"{prefix}terminal {event.get('terminal_id')} ONLINE"
    if event_type == "tool_call":
        return f"{prefix}tool {event.get('tool_name')} args={_shorten(event.get('arguments', {}), 80)}"
    if event_type == "tool_result":
        return f"{prefix}tool {event.get('tool_name')} result={_shorten(event.get('result', ''), 80)}"
    if event_type == "model_request":
        return (f"{prefix}model_request mode={event.get('mode')} tools={len(event.get('tools', []))} "
                f"last_messages={_shorten(event.get('last_messages', []), 80)}")
    if event_type == "model_response":
        return (
            f"{prefix}model_response tool_calls={[c.get('name') or c.get('function', {}).get('name', '') for c in event.get('tool_calls', [])]} "
            f"text={_shorten(event.get('text', ''), 80)}"
        )
    if event_type == "agent_warning":
        return f"{prefix}warning {event.get('warning_type')}: {_shorten(event.get('detail', ''), 80)}"
    if event_type == "model_thought":
        return f"{prefix}model_thought: {_shorten(event.get('thought', ''), 80)}"
    if event_type == "validation":
        return f"{prefix}validation: terminal_spec={_shorten(event.get('terminal_spec', ''))}"
    if event_type == "validation_result":
        return (f"{prefix}validation_result: exit code={event.get('exit_code')} terminal_spec={_shorten(event.get('terminal_spec', ''))} "
                f"stdout={_shorten(event.get('stdout', ''))} stderr={_shorten(event.get('stderr', ''))} "
                f"status={event.get('status', {})}")
    if event_type == "validation_summary":
        return (f"{prefix}validation_summary: passed={event.get('number_of_passed_validating_terminals')}/{event.get('total')} "
                f"failed_generator={event.get('failed_on_generator')} failed_task={event.get('failed_on_task')}")
    if event_type == "benchmark_current_score":
        return f"{prefix}benchmark_current_score: score={event.get('score')} best_score={event.get('best_score')} attempts={event.get('attempts', [])}"

    return f"{prefix}{event_type} {_shorten(event, 100)}"


class RunLogger:
    def __init__(self, *, path: str | None = None, console: bool = False) -> None:
        self.run_id = uuid.uuid4().hex
        self._console = console
        self._path = path
        self._fh = None
        self._lock = threading.Lock()
        self._current_iteration: int | None = None
        if path is not None:
            self._open(path)

    def _open(self, path: str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._fh = target.open("w", encoding="utf-8")

    @property
    def current_iteration(self) -> int | None:
        with self._lock:
            return self._current_iteration

    def set_output_path(self, path: str) -> None:
        with self._lock:
            if self._fh is not None:
                self._fh.close()
            self._path = path
            self._open(path)

    def enable_console(self) -> None:
        with self._lock:
            self._console = True

    def set_iteration(self, iteration: int | None) -> None:
        with self._lock:
            self._current_iteration = iteration

    def emit(
        self,
        *,
        event_type: str,
        actor: str,
        kind: str = "raw",
        iteration: int | None = None,
        force_emit_to_console: bool = False,
        **fields: Any,
    ) -> dict[str, Any]:
        event = {
            "time": _utc_now(),
            "run_id": self.run_id,
            "kind": kind,
            "event_type": event_type,
            "iteration": self.current_iteration if iteration is None else iteration,
            "actor": actor,
            **fields,
        }

        line = json.dumps(event, ensure_ascii=False)
        rendered = _render_console_event(event)
        with self._lock:
            if self._fh is not None:
                self._fh.write(line)
                self._fh.write("\n")
                self._fh.flush()
            if self._console and (actor != "terminal" or force_emit_to_console):
                print(rendered, file=sys.stderr, flush=True)
        return event

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                self._fh.close()
                self._fh = None


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_run_logger: RunLogger | None = None
_log_path: str | None = None
_log_to_stderr = False
_last_agent_error: str | None = None
_last_run_metrics: "RunTelemetry | None" = None


def _ensure_run_logger() -> RunLogger:
    global _run_logger
    if _run_logger is None:
        _run_logger = RunLogger(path=_log_path, console=_log_to_stderr)
    return _run_logger


def enable_logging() -> None:
    global _log_to_stderr
    _log_to_stderr = True
    _ensure_run_logger().enable_console()


def set_log_file(path: str) -> None:
    global _log_path
    _log_path = path
    _ensure_run_logger().set_output_path(path)


def get_run_logger() -> RunLogger:
    return _ensure_run_logger()


def emit_event(
    *,
    event_type: str,
    actor: str,
    kind: str = "raw",
    iteration: int | None = None,
    **fields,
) -> dict:
    return _ensure_run_logger().emit(
        event_type=event_type,
        actor=actor,
        kind=kind,
        iteration=iteration,
        **fields,
    )


def set_last_agent_error(message: str | None) -> None:
    global _last_agent_error
    _last_agent_error = message


def get_last_agent_error() -> str | None:
    return _last_agent_error


@dataclass
class RunTelemetry:
    started_at: str | None = None
    iterations: int = 0
    created_files: set[str] = field(default_factory=set)
    terminal_activation_steps: dict[str, int | None] = field(default_factory=dict)
    token_metrics: Usage = Usage()
    run_end_emitted: bool = False
    run_summary_emitted: bool = False


def set_last_run_metrics(metrics: "RunTelemetry | None") -> None:
    global _last_run_metrics
    _last_run_metrics = metrics


def get_last_run_metrics() -> "RunTelemetry | None":
    return _last_run_metrics


def _raw_usage_metadata(usage) -> dict:
    safe_usage = _json_safe(usage)
    return safe_usage if isinstance(safe_usage, dict) else {}


def _flatten_usage_metadata(raw_usage: dict) -> dict:
    flattened: dict = {}
    prompt_tokens_details = raw_usage.get("prompt_tokens_details")
    if isinstance(prompt_tokens_details, dict):
        cached_tokens = prompt_tokens_details.get("cached_tokens")
        if isinstance(cached_tokens, int):
            flattened["cached_input_tokens"] = cached_tokens
    completion_tokens_details = raw_usage.get("completion_tokens_details")
    if isinstance(completion_tokens_details, dict):
        reasoning_tokens = completion_tokens_details.get("reasoning_tokens")
        if isinstance(reasoning_tokens, int):
            flattened["reasoning_token_count"] = reasoning_tokens
    return flattened


def _build_usage_metadata(llm, usage) -> dict:
    usage_metadata: dict = {}
    if hasattr(llm, "_get_usage_meta"):
        normalized = llm._get_usage_meta(usage)
        if isinstance(normalized, dict):
            usage_metadata.update(normalized)

    raw_usage = _raw_usage_metadata(usage)
    usage_metadata.update(_flatten_usage_metadata(raw_usage))
    for key, value in raw_usage.items():
        if key not in usage_metadata:
            usage_metadata[key] = value
    return usage_metadata


def _merge_token_usage(metrics: RunTelemetry, usage_metadata: dict | None) -> None:
    if not isinstance(usage_metadata, dict):
        return
    for key, value in usage_metadata.items():
        if isinstance(value, int):
            metrics.token_metrics[key] = metrics.token_metrics.get(key, 0) + value
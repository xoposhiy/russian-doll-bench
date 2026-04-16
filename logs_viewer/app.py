"""
Standalone viewer app for structured benchmark run logs.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

_ROOT = Path(__file__).resolve().parent
_INDEX_FILE = _ROOT / "index.html"
_RUN_LOGS_DIR = _ROOT.parent / "logs"
_STATIC_DIR = _ROOT / "static"


class ValidationSummary(BaseModel):
    passed: int | None
    total: int | None


class RunLogSummary(BaseModel):
    run_index: int
    started_at: str | None
    ended_at: str | None
    model: str | None
    terminal_spec: str | None
    duration_seconds: float | None
    score: int | None
    max_score: int | None
    iterations: int | None
    sum_output_tokens: int | None
    sum_uncached_input_tokens: int | None
    sum_input_tokens: int | None
    total_tokens: int | None
    validation: ValidationSummary


class LogFileSummary(BaseModel):
    file_name: str
    started_at: str | None
    model: str | None
    sum_output_tokens: int
    sum_uncached_input_tokens: int
    sum_input_tokens: int
    total_tokens: int
    validation: ValidationSummary


class RunLogDetail(BaseModel):
    summary: RunLogSummary
    events: list[dict]


class RunLogsListResponse(BaseModel):
    runs: list[LogFileSummary]


class RunLogDetailResponse(BaseModel):
    summary: LogFileSummary
    runs: list[RunLogDetail]


app = FastAPI(title="Russian Doll Logs Viewer")


def _iter_jsonl_events(path: Path) -> list[dict]:
    events: list[dict] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        for raw_line in fh:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                events.append(json.loads(raw_line))
            except json.JSONDecodeError:
                continue
    return events


def _effective_total_tokens(event: dict) -> int | None:
    token_metrics = event.get("token_metrics")
    if isinstance(token_metrics, dict):
        for total_key in ("total_token_count", "total_tokens", "totalTokens"):
            if isinstance(token_metrics.get(total_key), int):
                return token_metrics[total_key]
        subtotal = 0
        found_any = False
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
                subtotal += value
                found_any = True
        if found_any:
            return subtotal
    total_tokens = event.get("total_tokens")
    if isinstance(total_tokens, int):
        return total_tokens
    return None


def _first_int(mapping: dict, keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, int):
            return value
    return None


def _effective_input_tokens(source: dict) -> int | None:
    return _first_int(
        source,
        (
            "sum_input_tokens",
            "input_tokens",
            "inputTokens",
            "prompt_token_count",
        ),
    )


def _effective_cached_input_tokens(source: dict) -> int | None:
    cached_input_tokens = _first_int(
        source,
        (
            "cached_content_token_count",
            "cached_input_tokens",
            "cache_read_input_tokens",
        ),
    )
    if cached_input_tokens is not None:
        return cached_input_tokens
    prompt_tokens_details = source.get("prompt_tokens_details")
    if isinstance(prompt_tokens_details, dict):
        cached_tokens = prompt_tokens_details.get("cached_tokens")
        if isinstance(cached_tokens, int):
            return cached_tokens
    return None


def _effective_uncached_input_tokens(source: dict) -> int | None:
    uncached = _first_int(
        source,
        (
            "sum_uncached_input_tokens",
            "uncached_input_tokens",
            "billable_input_tokens",
        ),
    )
    if uncached is not None:
        return uncached
    input_tokens = _effective_input_tokens(source)
    if input_tokens is None:
        return None
    cached_input_tokens = _effective_cached_input_tokens(source) or 0
    return max(input_tokens - cached_input_tokens, 0)


def _effective_output_tokens(source: dict) -> int | None:
    output_tokens = _first_int(
        source,
        (
            "sum_output_tokens",
            "output_tokens",
            "outputTokens",
        ),
    )
    if output_tokens is not None:
        return output_tokens

    candidates = _first_int(source, ("candidates_token_count",)) or 0
    thoughts = _first_int(source, ("thoughts_token_count", "reasoning_token_count")) or 0
    tool_calls = _first_int(
        source,
        (
            "tool_use_prompt_token_count",
            "tool_call_token_count",
        ),
    ) or 0
    total = candidates + thoughts + tool_calls
    return total or None


def _sum_model_response_tokens(events: list[dict]) -> int | None:
    total = 0
    found = False
    for event in events:
        if event.get("event_type") != "model_response":
            continue
        usage = event.get("usage_metadata")
        if not isinstance(usage, dict):
            continue
        for total_key in ("total_token_count", "total_tokens", "totalTokens"):
            value = usage.get(total_key)
            if isinstance(value, int):
                total += value
                found = True
                break
        else:
            subtotal = 0
            subtotal_found = False
            for key in (
                "inputTokens",
                "outputTokens",
                "input_tokens",
                "output_tokens",
                "prompt_token_count",
                "candidates_token_count",
            ):
                value = usage.get(key)
                if isinstance(value, int):
                    subtotal += value
                    subtotal_found = True
            if subtotal_found:
                total += subtotal
                found = True
    return total if found else None


def _sum_metric(events: list[dict], extractor) -> int | None:
    total = 0
    found = False
    for event in events:
        if event.get("event_type") != "model_response":
            continue
        usage = event.get("usage_metadata")
        if not isinstance(usage, dict):
            continue
        value = extractor(usage)
        if isinstance(value, int):
            total += value
            found = True
    return total if found else None


def _parse_runs(events: list[dict]) -> list[RunLogDetail]:
    run_start_indexes = [
        index for index, event in enumerate(events)
        if event.get("event_type") == "run_start"
    ]
    runs: list[RunLogDetail] = []
    for run_number, start_index in enumerate(run_start_indexes, start=1):
        next_start = (
            run_start_indexes[run_number]
            if run_number < len(run_start_indexes)
            else len(events)
        )
        run_events = events[start_index:next_start]
        if not run_events:
            continue

        run_start = run_events[0]
        run_end = next((event for event in run_events if event.get("event_type") == "run_end"), {})
        run_summary = next(
            (event for event in reversed(run_events) if event.get("event_type") == "run_summary"),
            {},
        )
        validation_summary_event = next(
            (event for event in reversed(run_events) if event.get("event_type") == "validation_summary"),
            {},
        )
        last_event = run_events[-1]
        token_metrics = run_summary.get("token_metrics")
        summary_token_source = token_metrics if isinstance(token_metrics, dict) else run_summary
        sum_output_tokens = _effective_output_tokens(summary_token_source)
        sum_uncached_input_tokens = _effective_uncached_input_tokens(summary_token_source)
        sum_input_tokens = _effective_input_tokens(summary_token_source)
        total_tokens = _effective_total_tokens(run_summary)
        if sum_output_tokens is None:
            sum_output_tokens = _sum_metric(run_events, _effective_output_tokens)
        if sum_uncached_input_tokens is None:
            sum_uncached_input_tokens = _sum_metric(run_events, _effective_uncached_input_tokens)
        if sum_input_tokens is None:
            sum_input_tokens = _sum_metric(run_events, _effective_input_tokens)
        if total_tokens is None:
            total_tokens = _sum_model_response_tokens(run_events)

        score = run_end.get("score", run_summary.get("score"))
        max_score = run_end.get("max_score", run_summary.get("max_score"))
        iterations = run_end.get("iteration", run_summary.get("iterations"))
        started_at = run_start.get("time")
        ended_at = last_event.get("time") or run_end.get("time")
        duration_seconds = None
        if started_at and ended_at:
            from datetime import datetime

            try:
                duration_seconds = round(
                    (datetime.fromisoformat(ended_at) - datetime.fromisoformat(started_at)).total_seconds(),
                    3,
                )
            except ValueError:
                duration_seconds = None

        runs.append(
            RunLogDetail(
                summary=RunLogSummary(
                    run_index=run_number,
                    started_at=started_at,
                    ended_at=ended_at,
                    model=run_start.get("model"),
                    terminal_spec=run_start.get("terminal_spec"),
                    duration_seconds=duration_seconds,
                    score=score,
                    max_score=max_score,
                    iterations=iterations,
                    sum_output_tokens=sum_output_tokens,
                    sum_uncached_input_tokens=sum_uncached_input_tokens,
                    sum_input_tokens=sum_input_tokens,
                    total_tokens=total_tokens,
                    validation=ValidationSummary(
                        passed=validation_summary_event.get("number_of_passed_validating_terminals"),
                        total=validation_summary_event.get("total"),
                    ),
                ),
                events=run_events,
            )
        )
    return runs


def _summarize_log_file(path: Path) -> LogFileSummary:
    runs = _parse_runs(_iter_jsonl_events(path))
    first_run = runs[0].summary if runs else None
    last_run = runs[-1].summary if runs else None
    return LogFileSummary(
        file_name=path.name,
        started_at=first_run.started_at if first_run else None,
        model=first_run.model if first_run else None,
        sum_output_tokens=sum(run.summary.sum_output_tokens or 0 for run in runs),
        sum_uncached_input_tokens=sum(run.summary.sum_uncached_input_tokens or 0 for run in runs),
        sum_input_tokens=sum(run.summary.sum_input_tokens or 0 for run in runs),
        total_tokens=sum(run.summary.total_tokens or 0 for run in runs),
        validation=ValidationSummary(
            passed=last_run.validation.passed if last_run else None,
            total=last_run.validation.total if last_run else None,
        ),
    )


app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    if not _INDEX_FILE.is_file():
        return PlainTextResponse("Logs viewer not found.", status_code=404)
    return FileResponse(_INDEX_FILE)


@app.get("/run-logs", response_model=RunLogsListResponse, include_in_schema=False)
def run_logs():
    runs = []
    if _RUN_LOGS_DIR.is_dir():
        for path in sorted(
            _RUN_LOGS_DIR.glob("*.jsonl"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ):
            runs.append(_summarize_log_file(path))
    return RunLogsListResponse(runs=runs)


@app.get("/run-logs/{file_name}", response_model=RunLogDetailResponse, include_in_schema=False)
def run_log_detail(file_name: str):
    if file_name.startswith("..") or "/" in file_name or "\\" in file_name:
        raise HTTPException(status_code=400, detail="Invalid log path.")

    path = (_RUN_LOGS_DIR / file_name).resolve()
    try:
        path.relative_to(_RUN_LOGS_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid log path.") from exc

    if path.suffix != ".jsonl" or not path.is_file():
        raise HTTPException(status_code=404, detail="Log not found.")

    events = _iter_jsonl_events(path)
    return RunLogDetailResponse(
        summary=_summarize_log_file(path),
        runs=_parse_runs(events),
    )

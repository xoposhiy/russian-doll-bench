#!/usr/bin/env python
"""
Analyze top-level benchmark JSONL logs from logs/.

The script is organized around:
- one generic parser that converts a log into episode traces;
- a list of hypothesis evaluators that aggregate per-model stats;
- separate tool-usage aggregation.
"""

from __future__ import annotations

import argparse
import ast
import csv
import io
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


MAIN_PY_RE = re.compile(r"(^|/)main\.py$", re.IGNORECASE)
TEXT_FILE_RE = re.compile(r"\.(md|txt|rst)$", re.IGNORECASE)
PY_FILE_RE = re.compile(r"\.py$", re.IGNORECASE)
AGENTS_MD_RE = re.compile(r"(^|/)agents\.md$", re.IGNORECASE)
FILE_REF_RE = re.compile(r"(?P<path>[A-Za-z0-9_./-]+\.[A-Za-z0-9_]+)")
HEREDOC_WRITE_RE = re.compile(
    r"cat\s+<<\s*['\"]?(?P<tag>[A-Za-z0-9_]+)['\"]?\s*>\s*(?P<path>[^\r\n]+)\r?\n(?P<body>.*?)\r?\n(?P=tag)",
    re.DOTALL,
)
MAIN_PY_REDIRECT_RE = re.compile(r"(?<!\d)>>(?!>)\s*main\.py\b|(?<!\d)>(?!>)\s*main\.py\b", re.IGNORECASE)
MAIN_PY_TEE_RE = re.compile(r"\btee\s+(?:-[A-Za-z]+\s+)*main\.py\b", re.IGNORECASE)
MAIN_PY_INLINE_WRITE_RE = re.compile(
    r"""
    open\(\s*['"]main\.py['"]\s*,\s*['"][^'"]*[wax+][^'"]*['"] |
    Path\(\s*['"]main\.py['"]\s*\)\.(?:write_text|write_bytes|touch)\s*\(
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)


@dataclass
class EpisodeTrace:
    episode_index: int
    terminal_spec: str | None
    solved_current_chain: bool
    run_score: int | None
    run_max_score: int | None
    iterations: int
    activated_terminals_count: int | None
    total_terminals: int | None
    validation_passed_before: int | None
    validation_total_before: int | None
    validation_passed_after: int | None
    validation_total_after: int | None
    benchmark_score_after: float | None
    benchmark_best_score_after: float | None
    preexisting_main_py: bool
    main_py_read: bool = False
    main_py_written: bool = False
    main_py_ran_after_last_write: bool = False
    created_files: list[str] = field(default_factory=list)
    ls_in_first_iterations: bool = False
    inherited_files: list[str] = field(default_factory=list)
    used_files: list[str] = field(default_factory=list)
    unused_inherited_files: list[str] = field(default_factory=list)
    main_local_imports: list[str] = field(default_factory=list)


@dataclass
class ScorePoint:
    agent_iteration: int
    score: float


@dataclass
class LogTrace:
    path: Path
    model: str
    episodes: list[EpisodeTrace]
    score_history: list[ScorePoint]
    tool_usage: Counter[str]
    run_usage: Counter[str]
    agent_warnings: Counter[str]


@dataclass
class ModelAggregate:
    model: str
    logs: list[LogTrace]
    episodes: list[EpisodeTrace]
    tool_usage: Counter[str]
    run_usage: Counter[str]
    agent_warnings: Counter[str]


@dataclass
class HypothesisRow:
    model: str
    metrics: dict[str, Any]


@dataclass
class HypothesisResult:
    key: str
    title: str
    definition: str
    rows: list[HypothesisRow]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze top-level JSONL logs in logs/.")
    parser.add_argument(
        "--logs-dir",
        default="logs",
        help="Directory to read. Only *.jsonl files directly inside it are used.",
    )
    parser.add_argument(
        "--out-dir",
        default="logs/log-analysis",
        help="Directory where reports will be written.",
    )
    parser.add_argument(
        "--ls-iterations",
        type=int,
        default=3,
        help="How many early iterations count as the 'first iterations' window for ls detection.",
    )
    return parser.parse_args()


def _normalize_file_name(value: str | None) -> str | None:
    if not value:
        return value
    return value.replace("\\", "/").strip()


def _is_main_py(filename: str | None) -> bool:
    normalized = _normalize_file_name(filename)
    return bool(normalized and MAIN_PY_RE.search(normalized))


def _is_text_file(filename: str | None) -> bool:
    normalized = _normalize_file_name(filename)
    return bool(normalized and TEXT_FILE_RE.search(normalized))


def _is_python_file(filename: str | None) -> bool:
    normalized = _normalize_file_name(filename)
    return bool(normalized and PY_FILE_RE.search(normalized))


def _is_agents_md(filename: str | None) -> bool:
    normalized = _normalize_file_name(filename)
    return bool(normalized and AGENTS_MD_RE.search(normalized))


def _iter_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        for raw_line in fh:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def _split_run_command(command: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    heredoc_tag: str | None = None
    escape = False
    i = 0
    while i < len(command):
        char = command[i]
        nxt = command[i + 1] if i + 1 < len(command) else ""
        line_end = command.find("\n", i)
        if line_end == -1:
            line_end = len(command)

        if heredoc_tag is not None:
            line = command[i:line_end]
            current.append(line)
            if line_end < len(command):
                current.append("\n")
            if line.strip() == heredoc_tag:
                heredoc_tag = None
            i = line_end + 1 if line_end < len(command) else line_end
            continue

        if escape:
            current.append(char)
            escape = False
            i += 1
            continue

        if char == "\\":
            current.append(char)
            escape = True
            i += 1
            continue

        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
            i += 1
            continue

        if char in {"'", '"'}:
            current.append(char)
            quote = char
            i += 1
            continue

        if char == "<" and nxt == "<":
            match = re.match(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", command[i:])
            if match:
                token = match.group(0)
                heredoc_tag = match.group(2)
                current.append(token)
                i += len(token)
                continue

        if char == ";" or (char == "&" and nxt == "&") or (char == "|" and nxt == "|"):
            chunk = "".join(current).strip()
            if chunk:
                parts.append(chunk)
            current = []
            i += 2 if char in {"&", "|"} else 1
            continue

        current.append(char)
        i += 1

    tail = "".join(current).strip()
    if tail:
        parts.append(tail)

    cleaned_parts: list[str] = []
    for chunk in parts:
        lines = []
        for line in chunk.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            lines.append(line)
        cleaned = "\n".join(lines).strip()
        if cleaned:
            cleaned_parts.append(cleaned)
    return cleaned_parts


def _classify_run_subcommand(command: str) -> str:
    token = command.split(maxsplit=1)[0] if command.strip() else ""
    token = token.lstrip("[('\"").rstrip(",;)]'\"")
    return token or "<empty>"


def _command_mentions_main_py(command: str) -> bool:
    return "main.py" in command.lower()


def _command_is_ls(command: str) -> bool:
    return _classify_run_subcommand(command).lower() == "ls"


def _extract_heredoc_writes(command: str) -> dict[str, str]:
    writes: dict[str, str] = {}
    for match in HEREDOC_WRITE_RE.finditer(command):
        path = _normalize_file_name(match.group("path").strip())
        if path:
            writes[path] = match.group("body")
    return writes


def _extract_file_references(command: str) -> set[str]:
    refs: set[str] = set()
    for match in FILE_REF_RE.finditer(command):
        path = _normalize_file_name(match.group("path"))
        if path:
            refs.add(path)
    return refs


def _extract_python_snippets(command: str) -> list[str]:
    snippets: list[str] = []

    for match in re.finditer(r"\bpython(?:3)?\s+-c\s+(['\"])(?P<code>.*?)\1", command, re.DOTALL | re.IGNORECASE):
        snippets.append(match.group("code"))

    for match in re.finditer(
        r"\bpython(?:3)?\s+-\s+<<-?\s*(['\"]?)(?P<tag>[A-Za-z_][A-Za-z0-9_]*)\1\r?\n(?P<body>.*?)\r?\n(?P=tag)",
        command,
        re.DOTALL | re.IGNORECASE,
    ):
        snippets.append(match.group("body"))

    return snippets


def _python_snippet_writes_main_py(code: str) -> bool:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False

    path_aliases: set[str] = set()

    def _const_str(node: ast.AST | None) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    def _is_main_py_path_expr(node: ast.AST | None) -> bool:
        if node is None:
            return False
        const_value = _const_str(node)
        if _is_main_py(const_value):
            return True
        if isinstance(node, ast.Name) and node.id in path_aliases:
            return True
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "Path" and node.args:
                return _is_main_py_path_expr(node.args[0])
            if isinstance(func, ast.Attribute) and func.attr in {"joinpath", "__truediv__"}:
                return _is_main_py_path_expr(func.value) or any(_is_main_py_path_expr(arg) for arg in node.args)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return _is_main_py_path_expr(node.left) or _is_main_py_path_expr(node.right)
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_main_py_path_expr(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    path_aliases.add(target.id)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open" and node.args:
            if _is_main_py_path_expr(node.args[0]):
                mode = _const_str(node.args[1]) if len(node.args) > 1 else "r"
                if mode and any(flag in mode for flag in ("w", "a", "x", "+")):
                    return True
        if isinstance(func, ast.Attribute) and func.attr in {"write_text", "write_bytes", "touch"}:
            if _is_main_py_path_expr(func.value):
                return True

    return False


def _command_writes_main_py(command: str) -> bool:
    lower = command.lower()
    if MAIN_PY_REDIRECT_RE.search(lower) or MAIN_PY_TEE_RE.search(lower) or MAIN_PY_INLINE_WRITE_RE.search(command):
        return True
    for snippet in _extract_python_snippets(command):
        if _python_snippet_writes_main_py(snippet):
            return True
    return False


def _apply_update(content: str | None, *, old: str, new: str) -> str | None:
    if content is None:
        return None
    if old not in content:
        return content
    return content.replace(old, new)


def _extract_local_imports(main_content: str | None, known_files: set[str]) -> list[str]:
    if not main_content:
        return []
    try:
        tree = ast.parse(main_content)
    except SyntaxError:
        return []

    imports: set[str] = set()

    def add_if_local(module_name: str) -> None:
        module_path = module_name.replace(".", "/")
        candidates = {
            f"{module_path}.py",
            f"{module_path}/__init__.py",
        }
        for candidate in candidates:
            if candidate in known_files and candidate != "main.py":
                imports.add(candidate)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add_if_local(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                if node.module:
                    add_if_local(node.module)
                else:
                    for alias in node.names:
                        add_if_local(alias.name.split(".", 1)[0])
            elif node.module:
                add_if_local(node.module.split(".", 1)[0])

    return sorted(imports)


def _aggregate_log(path: Path, *, ls_iterations: int) -> LogTrace | None:
    events = _iter_events(path)
    if not events:
        return None

    episodes: list[EpisodeTrace] = []
    score_history: list[ScorePoint] = []
    tool_usage: Counter[str] = Counter()
    run_usage: Counter[str] = Counter()
    agent_warnings: Counter[str] = Counter()

    current: dict[str, Any] | None = None
    last_validation_summary: tuple[int | None, int | None] | None = None
    model_name: str | None = None
    main_exists_from_previous_episode = False
    known_files: dict[str, str | None] = {}
    cumulative_agent_iterations = 0

    def finalize_current_episode() -> None:
        nonlocal current, main_exists_from_previous_episode
        if current is None:
            return
        current["main_local_imports"] = _extract_local_imports(
            known_files.get("main.py"),
            set(known_files),
        )
        used_files = set(current["used_files"])
        used_files.update(current["main_local_imports"])
        current["used_files"] = sorted(used_files)
        current["unused_inherited_files"] = sorted(
            filename for filename in current["inherited_files"]
            if filename not in used_files
        )
        episodes.append(_finalize_episode(current))
        main_exists_from_previous_episode = main_exists_from_previous_episode or episodes[-1].main_py_written

    for event in events:
        event_type = event.get("event_type")

        if event_type == "agent_warning":
            warning_type = str(event.get("warning_type") or "unknown")
            detail = str(event.get("detail") or "").strip()
            if warning_type == "tool_mode" and detail == "Using explicit genai function-call loop.":
                continue
            warning_label = _normalize_agent_warning(warning_type, detail)
            agent_warnings[warning_label] += 1
            continue

        if event_type == "validation_summary":
            passed = event.get("number_of_passed_validating_terminals")
            total = event.get("total")
            last_validation_summary = (
                passed if isinstance(passed, int) else None,
                total if isinstance(total, int) else None,
            )
            if current is not None:
                current["validation_after"] = last_validation_summary
            continue

        if event_type == "benchmark_current_score":
            score = event.get("score")
            if isinstance(score, (int, float)):
                score_history.append(ScorePoint(agent_iteration=cumulative_agent_iterations, score=float(score)))
            if current is not None:
                best = event.get("best_score")
                current["benchmark_score_after"] = float(score) if isinstance(score, (int, float)) else None
                current["benchmark_best_score_after"] = float(best) if isinstance(best, (int, float)) else None
            continue

        if event_type == "run_start":
            finalize_current_episode()
            model_name = str(event.get("model") or model_name or "unknown")
            current = {
                "episode_index": len(episodes) + 1,
                "terminal_spec": event.get("terminal_spec"),
                "solved_current_chain": False,
                "run_score": None,
                "run_max_score": None,
                "iterations": 0,
                "activated_terminals_count": None,
                "total_terminals": None,
                "validation_before": last_validation_summary,
                "validation_after": None,
                "benchmark_score_after": None,
                "benchmark_best_score_after": None,
                "preexisting_main_py": main_exists_from_previous_episode,
                "main_py_read": False,
                "main_py_written": False,
                "main_py_ran_after_last_write": False,
                "pending_main_py_run_check": False,
                "created_files": [],
                "ls_in_first_iterations": False,
                "inherited_files": sorted(known_files),
                "used_files": set(),
                "unused_inherited_files": [],
                "main_local_imports": [],
            }
            continue

        if current is None:
            continue

        if event_type == "run_end":
            current["solved_current_chain"] = bool(event.get("done"))
            current["run_score"] = event.get("score")
            current["run_max_score"] = event.get("max_score")
            continue

        if event_type == "run_summary":
            iterations = event.get("iterations")
            if isinstance(iterations, int):
                current["iterations"] = iterations
                cumulative_agent_iterations += iterations
            activated_terminals_count = event.get("activated_terminals_count")
            if isinstance(activated_terminals_count, int):
                current["activated_terminals_count"] = activated_terminals_count
            total_terminals = event.get("total_terminals")
            if isinstance(total_terminals, int):
                current["total_terminals"] = total_terminals
            created_files = event.get("created_files")
            if isinstance(created_files, list):
                normalized = []
                for filename in created_files:
                    clean = _normalize_file_name(str(filename))
                    if clean:
                        normalized.append(clean)
                        known_files.setdefault(clean, known_files.get(clean))
                        if _is_main_py(clean):
                            current["main_py_written"] = True
                current["created_files"] = normalized
            continue

        if event_type != "tool_call":
            continue

        tool_name = str(event.get("tool_name") or "")
        tool_usage[tool_name] += 1
        arguments = event.get("arguments")
        if not isinstance(arguments, dict):
            continue

        if tool_name in {"write_file", "update_file"}:
            filename = _normalize_file_name(str(arguments.get("filename"))) if "filename" in arguments else None
            if filename:
                current["used_files"].add(filename)
            if tool_name == "write_file" and filename:
                known_files[filename] = str(arguments.get("content") or "")
            elif tool_name == "update_file" and filename:
                known_files[filename] = _apply_update(
                    known_files.get(filename),
                    old=str(arguments.get("str_to_replace") or ""),
                    new=str(arguments.get("replacement") or ""),
                )
            if _is_main_py(filename):
                current["main_py_written"] = True
                current["main_py_ran_after_last_write"] = False
                current["pending_main_py_run_check"] = True
            continue

        if tool_name == "read_file":
            filename = _normalize_file_name(str(arguments.get("filename"))) if "filename" in arguments else None
            if filename:
                current["used_files"].add(filename)
            if _is_main_py(filename):
                current["main_py_read"] = True
            continue

        if tool_name == "run_python_file":
            filename = _normalize_file_name(str(arguments.get("filename"))) if "filename" in arguments else None
            if filename:
                current["used_files"].add(filename)
            if _is_main_py(filename):
                current["main_py_read"] = True
                if current["pending_main_py_run_check"]:
                    current["main_py_ran_after_last_write"] = True
                    current["pending_main_py_run_check"] = False
            continue

        if tool_name != "run":
            continue

        command = str(arguments.get("command") or "")
        for filename, content in _extract_heredoc_writes(command).items():
            known_files[filename] = content
            current["used_files"].add(filename)
            if _is_main_py(filename):
                current["main_py_written"] = True
                current["main_py_ran_after_last_write"] = False
                current["pending_main_py_run_check"] = True
        iteration = event.get("iteration")
        subcommands = _split_run_command(command)
        for subcommand in subcommands:
            subcommand_name = _classify_run_subcommand(subcommand)
            if subcommand_name == "<empty>":
                continue
            run_usage[subcommand_name] += 1
            current["used_files"].update(_extract_file_references(subcommand))
            if _command_writes_main_py(subcommand):
                current["main_py_written"] = True
                current["main_py_ran_after_last_write"] = False
                current["pending_main_py_run_check"] = True
            if current["preexisting_main_py"] and _command_mentions_main_py(subcommand):
                current["main_py_read"] = True
            if _command_mentions_main_py(subcommand) and current["pending_main_py_run_check"]:
                current["main_py_ran_after_last_write"] = True
                current["pending_main_py_run_check"] = False
            if isinstance(iteration, int) and iteration <= ls_iterations and _command_is_ls(subcommand):
                current["ls_in_first_iterations"] = True

    finalize_current_episode()

    if not episodes:
        return None

    return LogTrace(
        path=path,
        model=model_name or "unknown",
        episodes=episodes,
        score_history=score_history,
        tool_usage=tool_usage,
        run_usage=run_usage,
        agent_warnings=agent_warnings,
    )


def _finalize_episode(raw: dict[str, Any]) -> EpisodeTrace:
    passed_before, total_before = raw.get("validation_before") or (None, None)
    passed_after, total_after = raw.get("validation_after") or (None, None)
    return EpisodeTrace(
        episode_index=raw["episode_index"],
        terminal_spec=raw.get("terminal_spec"),
        solved_current_chain=bool(raw.get("solved_current_chain")),
        run_score=raw.get("run_score"),
        run_max_score=raw.get("run_max_score"),
        iterations=raw.get("iterations") or 0,
        activated_terminals_count=raw.get("activated_terminals_count"),
        total_terminals=raw.get("total_terminals"),
        validation_passed_before=passed_before,
        validation_total_before=total_before,
        validation_passed_after=passed_after,
        validation_total_after=total_after,
        benchmark_score_after=raw.get("benchmark_score_after"),
        benchmark_best_score_after=raw.get("benchmark_best_score_after"),
        preexisting_main_py=bool(raw.get("preexisting_main_py")),
        main_py_read=bool(raw.get("main_py_read")),
        main_py_written=bool(raw.get("main_py_written")),
        main_py_ran_after_last_write=bool(raw.get("main_py_ran_after_last_write")),
        created_files=list(raw.get("created_files") or []),
        ls_in_first_iterations=bool(raw.get("ls_in_first_iterations")),
        inherited_files=list(raw.get("inherited_files") or []),
        used_files=list(raw.get("used_files") or []),
        unused_inherited_files=list(raw.get("unused_inherited_files") or []),
        main_local_imports=list(raw.get("main_local_imports") or []),
    )


def _load_model_aggregates(*, logs_dir: Path, ls_iterations: int) -> list[ModelAggregate]:
    traces: list[LogTrace] = []
    for path in sorted(logs_dir.glob("*.jsonl")):
        trace = _aggregate_log(path, ls_iterations=ls_iterations)
        if trace is not None:
            traces.append(trace)

    grouped: dict[str, list[LogTrace]] = defaultdict(list)
    for trace in traces:
        grouped[_safe_model_label(trace.model)].append(trace)

    aggregates: list[ModelAggregate] = []
    for model, model_logs in sorted(grouped.items()):
        episodes = [episode for log in model_logs for episode in log.episodes]
        tool_usage: Counter[str] = Counter()
        run_usage: Counter[str] = Counter()
        agent_warnings: Counter[str] = Counter()
        for log in model_logs:
            tool_usage.update(log.tool_usage)
            run_usage.update(log.run_usage)
            agent_warnings.update(log.agent_warnings)
        aggregates.append(
            ModelAggregate(
                model=model,
                logs=model_logs,
                episodes=episodes,
                tool_usage=tool_usage,
                run_usage=run_usage,
                agent_warnings=agent_warnings,
            )
        )
    return aggregates


def _safe_model_label(model: str) -> str:
    return model.removeprefix("openai/").removeprefix("google/")


def _percent(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "-"
    return f"{(100.0 * numerator / denominator):.1f}%"


def _percent_value(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return -1.0
    return 100.0 * numerator / denominator


def _truncate_text(value: str, limit: int = 160) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _percent_str_to_value(value: str) -> float:
    if value == "-":
        return -1.0
    return float(value.rstrip("%"))


def _percent_blank_zero(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "-"
    if numerator == 0:
        return ""
    return _percent(numerator, denominator)


def _model_color_map(models: list[str]) -> dict[str, str]:
    palette = [
        "#4477AA",
        "#EE6677",
        "#228833",
        "#CCBB44",
        "#66CCEE",
        "#AA3377",
        "#BBBBBB",
        "#000000",
        "#EE7733",
        "#0077BB",
        "#33BBEE",
        "#009988",
    ]
    unique_models = sorted(dict.fromkeys(models))
    return {
        model: palette[index % len(palette)]
        for index, model in enumerate(unique_models)
    }


def _format_score(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _short_model_label(model: str) -> str:
    label = _safe_model_label(model)
    if "/" in label:
        label = label.split("/", 1)[1]
    if "@" in label:
        label = label.split("@", 1)[0]
    label = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", label)
    label = re.sub(r"-preview$", "", label)
    return label


def _logs_with_nonzero_scores(logs: list[LogTrace]) -> list[LogTrace]:
    return [
        log for log in logs
        if log.score_history and any(point.score != 0 for point in log.score_history)
    ]


def render_score_trajectories_svg(logs: list[LogTrace]) -> str:
    import matplotlib

    matplotlib.use("Agg")

    from matplotlib import pyplot as plt
    from matplotlib.lines import Line2D

    nonzero_logs = _logs_with_nonzero_scores(logs)
    best_model_score: dict[str, float] = {}
    best_model_log: dict[str, LogTrace] = {}
    for log in sorted(nonzero_logs, key=lambda item: (_safe_model_label(item.model), item.path.name)):
        model_best = max(point.score for point in log.score_history)
        if model_best > best_model_score.get(log.model, float("-inf")):
            best_model_score[log.model] = model_best
            best_model_log[log.model] = log

    top_models_ranked = [
        model
        for model, _score in sorted(
            best_model_score.items(),
            key=lambda item: (-item[1], _short_model_label(item[0])),
        )[:6]
    ]
    plotted_logs = [best_model_log[model] for model in top_models_ranked]
    color_map = _model_color_map(top_models_ranked)

    fig, ax = plt.subplots(figsize=(14, 8.2))
    fig.subplots_adjust(left=0.11, right=0.73, top=0.9, bottom=0.12)

    if not plotted_logs:
        ax.text(
            0.5,
            0.5,
            "No logs with non-zero benchmark score.",
            ha="center",
            va="center",
            fontsize=18,
            color="#444444",
            transform=ax.transAxes,
        )
        ax.axis("off")
    else:
        sorted_logs = sorted(plotted_logs, key=lambda item: (_safe_model_label(item.model), item.path.name))
        for log in sorted_logs:
            xs = [point.agent_iteration for point in log.score_history]
            ys = [point.score for point in log.score_history]
            line, = ax.plot(
                xs,
                ys,
                color=color_map[log.model],
                linewidth=2.2,
                alpha=0.82,
                linestyle="-",
            )
            line.set_gid(log.path.name)
            ax.scatter(xs, ys, color=color_map[log.model], s=18, alpha=0.9, zorder=4)

        end_labels: list[tuple[float, float, float, str, str]] = []
        for model in top_models_ranked:
            log = best_model_log[model]
            peak_point = max(log.score_history, key=lambda point: (point.score, -point.agent_iteration))
            end_labels.append((
                float(peak_point.agent_iteration),
                peak_point.score,
                peak_point.score,
                _short_model_label(model),
                color_map[model],
            ))

        ax.set_title("Benchmark Score Trajectories by Log", fontsize=18)
        ax.set_xlabel("Agent loop iteration (cumulative across all agent sessions)", fontsize=13)
        ax.set_ylabel("Benchmark score", fontsize=13)
        ax.grid(True, which="major", color="#d9d9d9", linewidth=0.8, alpha=0.7)
        ax.set_axisbelow(True)
        ax.margins(x=0.04)

        all_scores = [point.score for log in plotted_logs for point in log.score_history]
        y_min = min(0.0, min(all_scores))
        y_max = max(all_scores)
        if y_max <= y_min:
            y_max = y_min + 1.0
        ax.set_ylim(y_min, y_max * 1.03 if y_max > 0 else y_max + 1.0)
        y_span = max(ax.get_ylim()[1] - ax.get_ylim()[0], 1.0)
        min_gap = y_span * 0.025
        placed_y: list[float] = []
        adjusted_labels: list[tuple[float, float, float, str, str]] = []
        for x, point_y, label_y, label, color in sorted(end_labels, key=lambda item: item[2]):
            adjusted_y = label_y
            if placed_y and adjusted_y - placed_y[-1] < min_gap:
                adjusted_y = placed_y[-1] + min_gap
            placed_y.append(adjusted_y)
            adjusted_labels.append((x, point_y, adjusted_y, label, color))

        upper_limit = ax.get_ylim()[1] - y_span * 0.01
        for index in range(len(adjusted_labels) - 1, -1, -1):
            x, point_y, adjusted_y, label, color = adjusted_labels[index]
            if adjusted_y > upper_limit:
                adjusted_y = upper_limit
                adjusted_labels[index] = (x, point_y, adjusted_y, label, color)
                upper_limit = adjusted_y - min_gap
            else:
                upper_limit = adjusted_y - min_gap

        max_x = max(point.agent_iteration for log in plotted_logs for point in log.score_history)
        label_dx = max(1.0, max_x * 0.015)
        ax.set_xlim(right=max_x + label_dx * 10)

        for x, point_y, label_y, label, color in adjusted_labels:
            ax.scatter([x], [point_y], color=color, s=42, zorder=5)
            if abs(label_y - point_y) > y_span * 0.002:
                ax.plot(
                    [x, x + label_dx * 0.75],
                    [point_y, label_y],
                    color=color,
                    linewidth=0.9,
                    alpha=0.7,
                    zorder=4,
                )
            ax.annotate(
                label,
                xy=(x, point_y),
                xytext=(x + label_dx, label_y),
                textcoords="data",
                ha="left",
                va="center",
                fontsize=10,
                color=color,
                bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": "none", "alpha": 0.85},
            )

        legend_handles = [
            Line2D(
                [0],
                [0],
                color=color_map[model],
                lw=3,
                linestyle="-",
                label=_short_model_label(model),
            )
            for model in top_models_ranked
        ]
        ax.legend(
            handles=legend_handles,
            title="Models",
            loc="center left",
            bbox_to_anchor=(1.01, 0.5),
            frameon=False,
        )

    buffer = io.StringIO()
    fig.savefig(buffer, format="svg")
    plt.close(fig)
    return buffer.getvalue()


def write_score_trajectories_svg(aggregates: list[ModelAggregate], out_dir: Path) -> Path:
    path = out_dir / "score_trajectories_by_log.svg"
    logs = [log for aggregate in aggregates for log in aggregate.logs]
    path.write_text(render_score_trajectories_svg(logs), encoding="utf-8")
    return path


def _normalize_agent_warning(warning_type: str, detail: str) -> str:
    if warning_type in {"no_tool_call", "no_response"}:
        return warning_type
    return f"{warning_type}: {detail}" if detail else warning_type


def _next_generator_boundary(passed_before: int | None, total: int | None) -> int | None:
    if not isinstance(passed_before, int) or not isinstance(total, int):
        return None
    if total <= 0:
        return None
    generator_size = 50
    boundary = ((passed_before // generator_size) + 1) * generator_size
    return min(boundary, total)


def _generator_bucket(passed: int | None) -> int | None:
    if not isinstance(passed, int) or passed < 0:
        return None
    return passed // 50


def hypothesis_solved_but_validation_fails(aggregates: list[ModelAggregate]) -> HypothesisResult:
    rows = []
    for aggregate in aggregates:
        solved = [episode for episode in aggregate.episodes if episode.solved_current_chain]
        failing = [
            episode
            for episode in solved
            if (
                _next_generator_boundary(
                    episode.validation_passed_before,
                    episode.validation_total_before,
                )
                is not None
                and (
                    episode.validation_passed_after is None
                    or episode.validation_passed_after
                    < _next_generator_boundary(
                        episode.validation_passed_before,
                        episode.validation_total_before,
                    )
                )
            )
        ]
        rows.append(HypothesisRow(
            model=_safe_model_label(aggregate.model),
            metrics={
                "episodes_solved_chain": len(solved),
                "episodes_solved_chain_but_validation_failed": len(failing),
                "rate": _percent(len(failing), len(solved)),
            },
        ))
    rows = [row for row in rows if row.metrics["episodes_solved_chain"] > 0]
    rows.sort(key=lambda row: _percent_value(row.metrics["episodes_solved_chain_but_validation_failed"], row.metrics["episodes_solved_chain"]), reverse=True)
    return HypothesisResult(
        key="h1",
        title="H1: Creating infrastructure is harder than just solving the task",
        definition="Among episodes where the current training chain is solved (`run_end.done=true`), count how often validation still does not reach the next 50-task generator boundary. Example: if validation was 50/500 before the run, success means reaching at least 100/500 after the run.",
        rows=rows,
    )


def hypothesis_no_main_read(aggregates: list[ModelAggregate]) -> HypothesisResult:
    rows = []
    for aggregate in aggregates:
        eligible = [episode for episode in aggregate.episodes if episode.preexisting_main_py]
        missing = [episode for episode in eligible if not episode.main_py_read]
        rows.append(HypothesisRow(
            model=_safe_model_label(aggregate.model),
            metrics={
                "episodes_with_preexisting_main_py": len(eligible),
                "episodes_without_main_py_read": len(missing),
                "rate": _percent(len(missing), len(eligible)),
            },
        ))
    rows.sort(key=lambda row: _percent_value(row.metrics["episodes_without_main_py_read"], row.metrics["episodes_with_preexisting_main_py"]), reverse=True)
    return HypothesisResult(
        key="h2",
        title="H2: Models ignore existing infrastructure, focusing on resolving a task from scratch",
        definition="Among episodes that start after `main.py` already exists from an earlier episode, count how often the model never reads or explicitly references `main.py`.",
        rows=rows,
    )


def hypothesis_no_main_write(aggregates: list[ModelAggregate]) -> HypothesisResult:
    rows = []
    for aggregate in aggregates:
        eligible = [
            episode
            for episode in aggregate.episodes
            if (
                episode.activated_terminals_count is None
                or episode.total_terminals is None
                or episode.total_terminals <= 0
                or episode.activated_terminals_count == episode.total_terminals
            )
        ]
        missing = [episode for episode in eligible if not episode.main_py_written]
        rows.append(HypothesisRow(
            model=_safe_model_label(aggregate.model),
            metrics={
                "episodes_with_all_terminals_activated": len(eligible),
                "episodes_without_main_py_update": len(missing),
                "rate": _percent(len(missing), len(eligible)),
            },
        ))
    rows.sort(
        key=lambda row: _percent_value(
            row.metrics["episodes_without_main_py_update"],
            row.metrics["episodes_with_all_terminals_activated"],
        ),
        reverse=True,
    )
    return HypothesisResult(
        key="h3",
        title="H4: Models forget to update main.py",
        definition="Among episodes where all terminals were activated (`run_summary.activated_terminals_count == run_summary.total_terminals`), count how often `main.py` is neither created nor updated during the episode. Episodes that failed to activate the full terminal set are excluded.",
        rows=rows,
    )


def hypothesis_non_python_files_are_rare(aggregates: list[ModelAggregate]) -> HypothesisResult:
    rows = []
    for aggregate in aggregates:
        created_files = [filename for episode in aggregate.episodes for filename in episode.created_files]
        non_python = [filename for filename in created_files if not _is_python_file(filename)]
        unique_non_python = sorted(dict.fromkeys(non_python))
        rows.append(HypothesisRow(
            model=_safe_model_label(aggregate.model),
            metrics={
                "created_files_total": len(created_files),
                "non_python_files_list": ", ".join(unique_non_python) if unique_non_python else "-",
            },
        ))
    return HypothesisResult(
        key="h4",
        title="H5: Models almost never create non-Python files",
        definition="List every created file that is not `*.py`.",
        rows=rows,
    )


def hypothesis_no_early_ls(aggregates: list[ModelAggregate], *, ls_iterations: int) -> HypothesisResult:
    rows = []
    for aggregate in aggregates:
        missing = [episode for episode in aggregate.episodes if not episode.ls_in_first_iterations]
        rows.append(HypothesisRow(
            model=_safe_model_label(aggregate.model),
            metrics={
                "episodes_total": len(aggregate.episodes),
                f"episodes_without_ls_in_first_{ls_iterations}_iterations": len(missing),
                "rate": _percent(len(missing), len(aggregate.episodes)),
            },
        ))
    rows.sort(
        key=lambda row: _percent_value(
            row.metrics[f"episodes_without_ls_in_first_{ls_iterations}_iterations"],
            row.metrics["episodes_total"],
        ),
        reverse=True,
    )
    return HypothesisResult(
        key="h5",
        title="H3: Models do not explore the working directory early",
        definition=f"Count episodes with no `ls` subcommand inside the first {ls_iterations} agent iterations. `run` commands split on `&&`, `;`, and `||`.",
        rows=rows,
    )


def hypothesis_validation_score_movement(aggregates: list[ModelAggregate]) -> HypothesisResult:
    rows = []
    for aggregate in aggregates:
        comparable = [
            episode for episode in aggregate.episodes
            if isinstance(episode.validation_passed_before, int) and isinstance(episode.validation_passed_after, int)
        ]
        up = sum(
            1
            for episode in comparable
            if _generator_bucket(episode.validation_passed_after)
            > _generator_bucket(episode.validation_passed_before)
        )
        same = sum(
            1
            for episode in comparable
            if _generator_bucket(episode.validation_passed_after)
            == _generator_bucket(episode.validation_passed_before)
        )
        down = sum(
            1
            for episode in comparable
            if _generator_bucket(episode.validation_passed_after)
            < _generator_bucket(episode.validation_passed_before)
        )
        rows.append(HypothesisRow(
            model=_safe_model_label(aggregate.model),
            metrics={
                "episodes": len(comparable),
                "validation_score_up": _percent(up, len(comparable)),
                "validation_score_same": _percent(same, len(comparable)),
                "validation_score_down": _percent(down, len(comparable)),
            },
        ))
    rows.sort(key=lambda row: _percent_str_to_value(row.metrics["validation_score_down"]), reverse=True)
    return HypothesisResult(
        key="h6",
        title="H6: Models often break existing infrastructure (validation score degrades)",
        definition="Compare generator buckets, not raw validation counts: `0-49`, `50-99`, `100-149`, and so on. Moving within the same 50-task bucket counts as `same`; `up` and `down` only count transitions between these generator buckets.",
        rows=rows,
    )


def hypothesis_main_updated_but_not_run(aggregates: list[ModelAggregate]) -> HypothesisResult:
    rows = []
    for aggregate in aggregates:
        updated = [episode for episode in aggregate.episodes if episode.main_py_written]
        missing_run = [episode for episode in updated if not episode.main_py_ran_after_last_write]
        rows.append(HypothesisRow(
            model=_safe_model_label(aggregate.model),
            metrics={
                "episodes_with_main_py_update": len(updated),
                "episodes_main_py_updated_but_not_run": len(missing_run),
                "rate": _percent(len(missing_run), len(updated)),
            },
        ))
    rows.sort(key=lambda row: _percent_value(row.metrics["episodes_main_py_updated_but_not_run"], row.metrics["episodes_with_main_py_update"]), reverse=True)
    return HypothesisResult(
        key="h7",
        title="H7: Models dont test created infrastructure",
        definition="Among episodes that create or update `main.py`, count how often there is no later explicit execution of `main.py` in the same episode.",
        rows=rows,
    )


def hypothesis_unused_inherited_files(aggregates: list[ModelAggregate]) -> HypothesisResult:
    rows = []
    for aggregate in aggregates:
        eligible = [episode for episode in aggregate.episodes if episode.inherited_files]
        with_unused = [episode for episode in eligible if episode.unused_inherited_files]
        total_unused = sum(len(episode.unused_inherited_files) for episode in eligible)
        common_unused: Counter[str] = Counter()
        for episode in eligible:
            common_unused.update(episode.unused_inherited_files)
        rows.append(HypothesisRow(
            model=_safe_model_label(aggregate.model),
            metrics={
                "episodes_with_inherited_files": len(eligible),
                "episodes_with_unused_inherited_files": _percent(len(with_unused), len(eligible)),
                "avg_unused_inherited_files": round(total_unused / len(eligible), 2) if eligible else "-",
                "common_unused_files": ", ".join(f"{name}:{count}" for name, count in common_unused.most_common(5)) if common_unused else "-",
            },
        ))
    rows.sort(key=lambda row: _percent_str_to_value(row.metrics["episodes_with_unused_inherited_files"]), reverse=True)
    return HypothesisResult(
        key="h8",
        title="H8: Models do not cleanup the mess in the infrastructure",
        definition="Best-effort metric from logs: count files known from previous episodes that are never touched in the current episode, after also crediting local modules imported by the known `main.py` content as used.",
        rows=rows,
    )


def hypothesis_main_imports_local_modules(aggregates: list[ModelAggregate]) -> HypothesisResult:
    rows = []
    for aggregate in aggregates:
        known_main = [
            episode
            for episode in aggregate.episodes
            if episode.preexisting_main_py or episode.main_py_written
        ]
        with_local_imports = [episode for episode in known_main if episode.main_local_imports]
        imported_modules: Counter[str] = Counter()
        for episode in with_local_imports:
            imported_modules.update(episode.main_local_imports)
        rows.append(HypothesisRow(
            model=_safe_model_label(aggregate.model),
            metrics={
                "episodes_with_known_main_py": len(known_main),
                "episodes_where_main_imports_local_modules": len(with_local_imports),
                "rate": _percent(len(with_local_imports), len(known_main)),
                "local_modules_seen": ", ".join(f"{name}:{count}" for name, count in imported_modules.most_common(5)) if imported_modules else "-",
            },
        ))
    rows.sort(
        key=lambda row: _percent_value(
            row.metrics["episodes_where_main_imports_local_modules"],
            row.metrics["episodes_with_known_main_py"],
        ),
        reverse=True,
    )
    return HypothesisResult(
        key="h9",
        title="H9: Models do not decompose infrastructure into modules",
        definition="Best-effort metric from the reconstructable `main.py` content: among episodes where `main.py` is known to exist, count how often it imports local non-stdlib modules that correspond to files in the workspace state.",
        rows=rows,
    )


def build_hypotheses(aggregates: list[ModelAggregate], *, ls_iterations: int) -> list[HypothesisResult]:
    return [
        hypothesis_solved_but_validation_fails(aggregates),
        hypothesis_no_main_read(aggregates),
        hypothesis_no_early_ls(aggregates, ls_iterations=ls_iterations),
        hypothesis_no_main_write(aggregates),
        hypothesis_non_python_files_are_rare(aggregates),
        hypothesis_validation_score_movement(aggregates),
        hypothesis_main_updated_but_not_run(aggregates),
        hypothesis_unused_inherited_files(aggregates),
        hypothesis_main_imports_local_modules(aggregates),
    ]


def write_hypotheses_markdown(results: list[HypothesisResult], out_dir: Path, *, logs_dir: Path) -> Path:
    path = out_dir / "hypotheses_report.md"
    lines = [
        "# Log Hypotheses Report",
        "",
        f"Source: top-level `*.jsonl` files directly in `{logs_dir.as_posix()}`.",
        "",
    ]
    for result in results:
        lines.append(f"## {result.title}")
        lines.append("")
        lines.append(result.definition)
        lines.append("")
        if result.rows:
            headers = ["model", *result.rows[0].metrics.keys()]
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join("---" for _ in headers) + " |")
            for row in result.rows:
                values = [row.model, *[str(row.metrics[key]) for key in result.rows[0].metrics]]
                lines.append("| " + " | ".join(values) + " |")
        else:
            lines.append("_No data._")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_tool_usage_csv(aggregates: list[ModelAggregate], out_dir: Path) -> Path:
    path = out_dir / "tool_usage_by_model.csv"
    tool_names = sorted({tool for aggregate in aggregates for tool in aggregate.tool_usage})
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["model", *tool_names])
        for aggregate in aggregates:
            writer.writerow([_safe_model_label(aggregate.model), *[aggregate.tool_usage.get(tool, 0) for tool in tool_names]])
    return path


def write_run_usage_csv(aggregates: list[ModelAggregate], out_dir: Path) -> Path:
    path = out_dir / "run_subcommands_by_model.csv"
    total_counts: Counter[str] = Counter()
    for aggregate in aggregates:
        total_counts.update(aggregate.run_usage)
    grouped_commands = {
        command
        for command, count in total_counts.items()
        if count == 1 or len(command) > 20
    }
    grouped_counts: dict[str, Counter[str]] = {}
    for aggregate in aggregates:
        grouped = Counter()
        for command, count in aggregate.run_usage.items():
            grouped["*" if command in grouped_commands else command] += count
        grouped_counts[aggregate.model] = grouped
    grouped_totals: Counter[str] = Counter()
    for grouped in grouped_counts.values():
        grouped_totals.update(grouped)
    grouped_presence: Counter[str] = Counter()
    for grouped in grouped_counts.values():
        for command, count in grouped.items():
            if count > 0:
                grouped_presence[command] += 1
    ranked_commands = sorted(
        (command for command in grouped_totals if command != "*"),
        key=lambda command: (-grouped_presence[command], -grouped_totals[command], command),
    )
    top_commands = ranked_commands[:15]
    command_names = [*top_commands]
    if "*" in grouped_totals or len(ranked_commands) > len(top_commands):
        command_names.append("*")
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["model", *command_names])
        for aggregate in aggregates:
            grouped = grouped_counts[aggregate.model]
            other_count = sum(
                count
                for command, count in grouped.items()
                if command not in top_commands and command != "*"
            )
            if "*" in command_names:
                row_counts = [
                    grouped.get(command, 0) if command != "*" else grouped.get("*", 0) + other_count
                    for command in command_names
                ]
            else:
                row_counts = [grouped.get(command, 0) for command in command_names]
            writer.writerow([_safe_model_label(aggregate.model), *row_counts])
    return path


def write_tool_usage_markdown(aggregates: list[ModelAggregate], out_dir: Path) -> Path:
    path = out_dir / "tool_usage_report.md"
    lines = [
        "# Tool Usage Report",
        "",
        "## Tool calls",
        "",
    ]
    tool_names = sorted({tool for aggregate in aggregates for tool in aggregate.tool_usage})
    if tool_names:
        headers = ["model", "tool_calls_total", *tool_names]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for aggregate in aggregates:
            total = sum(aggregate.tool_usage.values())
            values = [
                _safe_model_label(aggregate.model),
                str(total),
                *[_percent_blank_zero(aggregate.tool_usage.get(tool, 0), total) for tool in tool_names],
            ]
            lines.append("| " + " | ".join(values) + " |")
    else:
        lines.append("_No tool calls found._")
    lines.extend(["", "## `run` subcommands", ""])
    total_counts: Counter[str] = Counter()
    for aggregate in aggregates:
        total_counts.update(aggregate.run_usage)
    grouped_commands = {
        command
        for command, count in total_counts.items()
        if count == 1 or len(command) > 20
    }
    grouped_counts: dict[str, Counter[str]] = {}
    for aggregate in aggregates:
        grouped = Counter()
        for command, count in aggregate.run_usage.items():
            grouped["*" if command in grouped_commands else command] += count
        grouped_counts[aggregate.model] = grouped
    grouped_totals: Counter[str] = Counter()
    for grouped in grouped_counts.values():
        grouped_totals.update(grouped)
    grouped_presence: Counter[str] = Counter()
    for grouped in grouped_counts.values():
        for command, count in grouped.items():
            if count > 0:
                grouped_presence[command] += 1
    ranked_commands = sorted(
        (command for command in grouped_totals if command != "*"),
        key=lambda command: (-grouped_presence[command], -grouped_totals[command], command),
    )
    top_commands = ranked_commands[:15]
    command_names = [*top_commands]
    if "*" in grouped_totals or len(ranked_commands) > len(top_commands):
        command_names.append("*")
    if command_names:
        headers = ["model", "run_subcommands_total", *command_names]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for aggregate in aggregates:
            grouped = grouped_counts[aggregate.model]
            other_count = sum(
                count
                for command, count in grouped.items()
                if command not in top_commands and command != "*"
            )
            if "*" in command_names:
                counts = [
                    grouped.get(command, 0) if command != "*" else grouped.get("*", 0) + other_count
                    for command in command_names
                ]
            else:
                counts = [grouped.get(command, 0) for command in command_names]
            total = sum(counts)
            values = [
                _safe_model_label(aggregate.model),
                str(total),
                *[_percent_blank_zero(count, total) for count in counts],
            ]
            lines.append("| " + " | ".join(values) + " |")
    else:
        lines.append("_No `run` commands found._")
    lines.extend(["", "## `agent_warning`", ""])
    for aggregate in aggregates:
        total_warnings = sum(aggregate.agent_warnings.values())
        total_tool_calls = sum(aggregate.tool_usage.values())
        lines.append(f"### {_safe_model_label(aggregate.model)}")
        lines.append("")
        lines.append(f"total: {total_warnings}")
        lines.append("")
        headers = ["warning", "count", "pct_of_tool_calls"]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        if aggregate.agent_warnings:
            for warning, count in aggregate.agent_warnings.most_common():
                lines.append("| " + " | ".join([
                    _truncate_text(warning),
                    f"{count}/{total_tool_calls}",
                    _percent(count, total_tool_calls),
                ]) + " |")
        else:
            lines.append(f"| - | 0/{total_tool_calls} | - |")
        lines.append("")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def print_console_summary(results: list[HypothesisResult], aggregates: list[ModelAggregate]) -> None:
    print("Hypotheses")
    for result in results:
        print()
        print(result.title)
        for row in result.rows:
            metrics = ", ".join(f"{key}={value}" for key, value in row.metrics.items())
            print(f"  {row.model}: {metrics}")
    print()
    print("Tool usage")
    for aggregate in aggregates:
        top_tools = ", ".join(f"{tool}:{count}" for tool, count in aggregate.tool_usage.most_common(6)) or "-"
        top_run = ", ".join(f"{command}:{count}" for command, count in aggregate.run_usage.most_common(8)) or "-"
        print(f"  {_safe_model_label(aggregate.model)}: tools[{top_tools}] run[{top_run}]")


def main() -> int:
    args = parse_args()
    logs_dir = Path(args.logs_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    aggregates = _load_model_aggregates(logs_dir=logs_dir, ls_iterations=args.ls_iterations)
    if not aggregates:
        print(f"No JSONL logs found directly inside {logs_dir}.")
        return 1

    results = build_hypotheses(aggregates, ls_iterations=args.ls_iterations)
    hypotheses_md = write_hypotheses_markdown(results, out_dir, logs_dir=logs_dir)
    tool_usage_md = write_tool_usage_markdown(aggregates, out_dir)
    tool_usage_csv = write_tool_usage_csv(aggregates, out_dir)
    run_usage_csv = write_run_usage_csv(aggregates, out_dir)
    score_svg = write_score_trajectories_svg(aggregates, out_dir)

    print_console_summary(results, aggregates)
    print()
    print(f"Wrote {hypotheses_md}")
    print(f"Wrote {tool_usage_md}")
    print(f"Wrote {tool_usage_csv}")
    print(f"Wrote {run_usage_csv}")
    print(f"Wrote {score_svg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

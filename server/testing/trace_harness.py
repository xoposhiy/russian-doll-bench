"""Shared helpers for deterministic terminal trace tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from benchmark.telemetry import RunLogger
from server.base_terminal import BaseTerminal
from server.sessions import LogEntry, SessionTerminalLogger


@dataclass(frozen=True)
class TraceEvent:
    kind: Literal["io", "note", "tool"]
    text: str
    visible_to_agent: bool
    terminal_id: str | None = None
    direction: Literal["in", "out"] | None = None


class StepResult:
    def __init__(self, text: str) -> None:
        self._text = text

    @property
    def text(self) -> str:
        return self._text

    def expect(self, *parts: str) -> "StepResult":
        for part in parts:
            assert part in self._text
        return self

    def expect_not(self, *parts: str) -> "StepResult":
        for part in parts:
            assert part not in self._text
        return self


def render_trace(
    *,
    terminal_type: str,
    seed: int,
    iterations: int,
    events: list[TraceEvent],
) -> str:
    lines = [f"Terminal type and seed: {terminal_type}, seed={seed}"]
    previous_event: TraceEvent | None = None

    for event in events:
        starts_new_block = event.kind in {"note", "tool"} or (
            event.kind == "io" and event.visible_to_agent and event.direction == "in"
        )
        if previous_event is not None and starts_new_block:
            lines.append("")

        if event.kind == "note":
            note_lines = event.text.splitlines() or [""]
            lines.append(f"   [hidden] [note] {note_lines[0]}")
            for note_line in note_lines[1:]:
                lines.append(f"          {note_line}")
        elif event.kind == "tool":
            tool_lines = event.text.splitlines() or [""]
            lines.append(f"   [tool] {tool_lines[0]}")
            for tool_line in tool_lines[1:]:
                lines.append(f"          {tool_line}")
        else:
            marker = "<<" if event.direction == "in" else ">>"
            prefix = "[terminal] "
            if not event.visible_to_agent:
                prefix = "[hidden] [terminal] "
            message_lines = event.text.splitlines()
            if not message_lines:
                message_lines = [""]
            lines.append(f"   {prefix}{event.terminal_id} {marker} {message_lines[0]}".rstrip())
            for message_line in message_lines[1:]:
                lines.append(f"      {message_line}")

        previous_event = event

    lines.append(f"Number of iterations spent to solve: {iterations}")
    return "\n".join(lines) + "\n"


def write_solution_trace_if_changed(path: Path, content: str) -> str:
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current != content:
        path.write_text(content, encoding="utf-8")
    return content


class TraceHarness:
    def __init__(
        self,
        *,
        terminal: BaseTerminal,
        trace_path: Path,
        seed: int,
        terminal_type: str | None = None,
    ) -> None:
        self.terminal = terminal
        self.trace_path = trace_path
        self.seed = seed
        self.terminal_type = terminal_type or type(terminal).__name__
        self.root_terminal_id = terminal.terminal_id

        self._run_logger = RunLogger()
        self._log_entries: list[LogEntry] = []
        self._log_offset = 0
        self._events: list[TraceEvent] = []
        self._iterations = 0

        terminal.attach_terminal_logger(SessionTerminalLogger(self._log_entries, self._run_logger))

    @property
    def events(self) -> list[TraceEvent]:
        return list(self._events)

    @property
    def iterations(self) -> int:
        return self._iterations

    def note(self, text: str) -> None:
        self._events.append(TraceEvent(kind="note", text=text, visible_to_agent=False))

    def write_file(self, path: str, summary: str | None = None) -> None:
        self._record_tool_step("write_file", path, summary)

    def run_command(self, command: str, summary: str | None = None) -> None:
        self._record_tool_step("run_command", command, summary)

    def step(self, payload: str) -> StepResult:
        self._iterations += 1
        self._run_logger.set_iteration(self._iterations)
        try:
            response = self.terminal.execute(payload)
        finally:
            self._run_logger.set_iteration(None)

        self._capture_new_entries()
        return StepResult(response)

    def render(self) -> str:
        return render_trace(
            terminal_type=self.terminal_type,
            seed=self.seed,
            iterations=self._iterations,
            events=self._events,
        )

    def write_solution_trace(self) -> str:
        return write_solution_trace_if_changed(self.trace_path, self.render())

    def _capture_new_entries(self) -> None:
        new_entries = self._log_entries[self._log_offset :]
        self._log_offset = len(self._log_entries)
        for entry in new_entries:
            self._events.append(
                TraceEvent(
                    kind="io",
                    text=entry.message,
                    visible_to_agent=entry.terminal_id == self.root_terminal_id,
                    terminal_id=entry.terminal_id,
                    direction=entry.direction,
                )
            )

    def _record_tool_step(self, action: str, target: str, summary: str | None) -> None:
        self._iterations += 1
        text = f"{action} {target}"
        if summary:
            text = f"{text} - {summary}"
        self._events.append(TraceEvent(kind="tool", text=text, visible_to_agent=False))

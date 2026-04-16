"""
Interaction log and session wrapper for the terminal HTTP server.
"""

from __future__ import annotations

import contextlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Generator

from benchmark.telemetry import RunLogger
from server.base_terminal import BaseTerminal


@dataclass
class LogEntry:
    event_type: str
    terminal_id: str
    terminal_kind: str
    message: str
    timestamp: float = field(default_factory=time.time)
    iteration: int | None = None

    @property
    def direction(self) -> str:
        return "in" if self.event_type == "terminal_input" else "out"

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "terminal_id": self.terminal_id,
            "terminal_kind": self.terminal_kind,
            "direction": self.direction,
            "message": self.message,
            "timestamp": self.timestamp,
            "iteration": self.iteration,
        }


class SessionTerminalLogger:
    def __init__(self, sink: list[LogEntry], run_logger: RunLogger | None = None) -> None:
        self._sink = sink
        self._run_logger = run_logger

    @property
    def entries(self):
        return self._sink

    def emit_terminal_event(
        self,
        *,
        event_type: str,
        terminal: BaseTerminal,
        payload: str,
    ) -> None:
        iteration = self._run_logger.current_iteration if self._run_logger is not None else None
        entry = LogEntry(
            event_type=event_type,
            terminal_id=terminal.terminal_id,
            terminal_kind=type(terminal).__name__,
            message=payload,
            iteration=iteration,
        )
        self._sink.append(entry)
        if self._run_logger is not None:
            self._run_logger.emit(
                event_type=event_type,
                actor="terminal",
                iteration=iteration,
                terminal_id=terminal.terminal_id,
                terminal_kind=type(terminal).__name__,
                payload=payload,
            )


@dataclass
class Session:
    outer_terminal: BaseTerminal
    run_logger: RunLogger | None = None
    log: list[LogEntry] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock, compare=False, repr=False)

    def __post_init__(self) -> None:
        self._terminal_logger = SessionTerminalLogger(self.log, self.run_logger)
        self.outer_terminal.attach_terminal_logger(self._terminal_logger)

    def replace_outer_terminal(self, outer_terminal: BaseTerminal):
        with self.lock:
            self.log = []
            self.outer_terminal = outer_terminal
            self.outer_terminal.attach_terminal_logger(self._terminal_logger)

    @contextlib.contextmanager
    def disable_logging(self):
        with self.lock:
            self.outer_terminal.attach_terminal_logger(None)

        yield

        with self.lock:
            self.outer_terminal.attach_terminal_logger(self._terminal_logger)

    @contextlib.contextmanager
    def with_logger(self):
        temporary_terminal_logger = SessionTerminalLogger([], RunLogger())
        with self.lock:
            self.outer_terminal.attach_terminal_logger(temporary_terminal_logger)

        yield temporary_terminal_logger

        with self.lock:
            self.outer_terminal.attach_terminal_logger(self._terminal_logger)

    def send(self, message: str) -> str:
        with self.lock:
            return self.outer_terminal.execute(message)

    def snapshot_log(self) -> list[LogEntry]:
        with self.lock:
            return list(self.log)

    def status(self) -> dict:
        with self.lock:
            terminals = self.outer_terminal.all_terminals()
            return {
                "terminal_ids": [t.terminal_id for t in terminals],
                "online_flags": [t.is_online for t in terminals],
                "online": sum(1 for t in terminals if t.is_online),
                "total": len(terminals),
                "done": all(t.is_online for t in terminals),
            }

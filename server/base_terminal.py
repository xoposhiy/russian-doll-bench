"""
Abstract base class for all benchmark terminals.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseTerminal(ABC):
    """
    Abstract base class for all benchmark terminals.

    Interface:
        __init__(name, seed, nested)
        terminal_id           : str           — unique system identifier
        is_online             : bool          — True once the terminal's puzzle is solved
        child_terminal        : Terminal|None — the directly nested subsystem
        get_welcome_message() → str           — returned when terminal is first accessed
        send(payload) → str                   — process a command and return a response
        all_terminals()       → list          — self + all nested terminals in chain order

    Terminals are self-contained state machines. They do NOT interact with the agent's
    VirtualFileSystem — all their state is stored internally.

    The system starts with the outermost terminal accessible and all nested terminals
    locked. Solving a terminal's puzzle activates its child terminal (the child's welcome
    message is included in the success response).
    """

    def __init__(self, name: str, seed: int, nested: "BaseTerminal | None" = None):
        self._terminal_id = name
        self._seed = seed
        self._nested = nested
        self._terminal_logger = None
        self._online = False

    def reset(self):
        self._online = False
        if self._nested is not None:
            self._nested.reset()

    @property
    def terminal_id(self) -> str:
        """Unique identifier used in all messages from this terminal."""
        return self._terminal_id

    @property
    def is_online(self) -> bool:
        """True once this terminal's activation condition has been met."""
        return self._online

    @property
    def child_terminal(self) -> "BaseTerminal | None":
        """The directly nested terminal, or None if this is the innermost."""
        return self._nested

    @abstractmethod
    def get_welcome_message(self) -> str:
        """Return the welcome/specs text shown when the terminal is first accessed."""

    @abstractmethod
    def send(self, payload: str) -> str:
        """Process a payload string and return a response string."""

    def attach_terminal_logger(self, logger: Any) -> None:
        """Attach a session-scoped terminal logger to this terminal chain."""
        self._terminal_logger = logger
        child = self.child_terminal
        if child is not None:
            child.attach_terminal_logger(logger)

    def execute(self, payload: str) -> str:
        """Handle payload while emitting terminal input/output events if configured."""
        logger = self._terminal_logger
        if logger is not None:
            logger.emit_terminal_event(event_type="terminal_input", terminal=self, payload=payload)
        response = self.send(payload)
        if logger is not None:
            logger.emit_terminal_event(event_type="terminal_output", terminal=self, payload=response)
        return response

    def dispatch_child(self, payload: str) -> str:
        """Send payload to the directly nested terminal through the same logger-aware path."""
        child = self.child_terminal
        if child is None:
            raise RuntimeError("No nested terminal is connected.")
        return child.execute(payload)

    def all_terminals(self) -> "list[BaseTerminal]":
        """Return [self, child, child.child, ...] walking the full chain."""
        result: list[BaseTerminal] = [self]
        node = self.child_terminal
        while node is not None:
            result.append(node)
            node = node.child_terminal
        return result

    def __str__(self):
        """Return a string representation (similar to terminal spec) of this terminal."""
        terminals = self.all_terminals()

        parts = []
        for terminal in terminals:
            class_name = terminal.__class__.__name__.removesuffix("Terminal").lower()
            parts.append(f"{class_name}({terminal._seed})")

        return "-".join(parts)

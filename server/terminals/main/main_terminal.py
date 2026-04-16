"""
Main Terminal - the innermost node of the full benchmark matryoshka.

Activation command: ACTIVATE TERMINAL
"""

from server.base_terminal import BaseTerminal


class MainTerminal(BaseTerminal):
    """Final innermost terminal. Goes online when agent sends 'ACTIVATE TERMINAL'."""

    def __init__(self, name: str, seed: int, nested=None) -> None:
        super().__init__(name=name, seed=seed, nested=None)
        # seed and nested are intentionally unused

    @property
    def child_terminal(self):
        return None

    def get_welcome_message(self) -> str:
        return (
            f"[{self._terminal_id}] Final system terminal. "
            "Send HELP for available commands."
        )

    def send(self, payload: str) -> str:
        cmd = payload.strip()

        if not cmd:
            return self.get_welcome_message()

        if cmd == "HELP":
            return (
                f"[{self._terminal_id}] Available commands:\n"
                "  ACTIVATE TERMINAL - activate this system\n"
                "  HELP              - show this message"
            )

        if cmd == "ACTIVATE TERMINAL":
            self._online = True
            return (
                f"[{self._terminal_id}] Congratulations! "
                "You have activated the final terminal. Task complete."
            )

        return (
            f"[{self._terminal_id}] Unknown command: {cmd!r}. "
            "Send HELP for available commands."
        )

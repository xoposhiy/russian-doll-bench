"""Minimal wrapper terminal with raw forwarding after activation."""

from server.base_terminal import BaseTerminal


class DummyTerminal(BaseTerminal):
    """Minimal terminal that activates once and then forwards raw SEND payloads."""

    def __init__(self, name: str, seed: int, nested=None) -> None:
        super().__init__(name=name, seed=seed, nested=nested)
        # seed is intentionally unused

    def get_welcome_message(self) -> str:
        return f"[{self._terminal_id}] Basic terminal. Send HELP for available commands."

    def send(self, payload: str) -> str:
        command = payload.strip()
        if not command:
            return self.get_welcome_message()

        if command == "HELP":
            return (
                f"[{self._terminal_id}] Commands:\n"
                "  HELP               - show this message\n"
                "  ACTIVATE TERMINAL  - activate this system\n"
                "  SEND <data>        - forward raw data to the child terminal"
            )

        if command == "ACTIVATE TERMINAL":
            self._online = True
            if self._nested is None:
                return f"[{self._terminal_id}] Link active."
            return f"[{self._terminal_id}] Link active.\n{self._nested.get_welcome_message()}"

        if command == "SEND":
            return f"[{self._terminal_id}] SEND requires data. Use SEND <data>."

        if command.startswith("SEND "):
            if not self._online:
                return f"[{self._terminal_id}] SEND is unavailable. Use ACTIVATE TERMINAL first."
            if self._nested is None:
                return f"[{self._terminal_id}] SEND failed: no child terminal connected."
            return self.dispatch_child(command[5:])

        return (
            f"[{self._terminal_id}] Unknown command: {command!r}. "
            "Send HELP for available commands."
        )

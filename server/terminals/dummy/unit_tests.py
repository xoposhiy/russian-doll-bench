"""Unit tests for DummyTerminal."""

from server.terminals.dummy import DummyTerminal
from server.terminals.main import MainTerminal


def make_main() -> MainTerminal:
    return MainTerminal("INNER", seed=0)


def make_terminal(nested=None) -> DummyTerminal:
    return DummyTerminal("DUMMY", seed=0, nested=nested)


class TestWelcomeAndHelp:
    def test_empty_payload_returns_welcome(self):
        response = make_terminal().send("")
        assert response == "[DUMMY] Basic terminal. Send HELP for available commands."

    def test_help_lists_supported_commands(self):
        response = make_terminal().send("HELP")
        assert "HELP" in response
        assert "ACTIVATE TERMINAL" in response
        assert "SEND <data>" in response


class TestActivation:
    def test_activate_sets_terminal_online(self):
        terminal = make_terminal()
        terminal.send("ACTIVATE TERMINAL")
        assert terminal.is_online is True

    def test_activate_returns_child_welcome_when_present(self):
        response = make_terminal(nested=make_main()).send("ACTIVATE TERMINAL")
        assert "[INNER] Final system terminal." in response


class TestSend:
    def test_send_is_blocked_before_activation(self):
        response = make_terminal(nested=make_main()).send("SEND HELP")
        assert response == "[DUMMY] SEND is unavailable. Use ACTIVATE TERMINAL first."

    def test_send_requires_data(self):
        response = make_terminal().send("SEND")
        assert response == "[DUMMY] SEND requires data. Use SEND <data>."

    def test_send_forwards_raw_data_to_child(self):
        terminal = make_terminal(nested=make_main())
        terminal.send("ACTIVATE TERMINAL")
        response = terminal.send("SEND HELP")
        assert "ACTIVATE TERMINAL" in response

    def test_send_can_activate_nested_terminal(self):
        nested = make_main()
        terminal = make_terminal(nested=nested)
        terminal.send("ACTIVATE TERMINAL")
        response = terminal.send("SEND ACTIVATE TERMINAL")
        assert nested.is_online is True
        assert "Task complete" in response

    def test_send_reports_missing_child(self):
        terminal = make_terminal()
        terminal.send("ACTIVATE TERMINAL")
        response = terminal.send("SEND HELP")
        assert response == "[DUMMY] SEND failed: no child terminal connected."

"""Unit tests for MainTerminal."""

import pytest
from server.terminals.main import MainTerminal


def make_terminal(name="MAIN") -> MainTerminal:
    return MainTerminal(name, seed=0)


class TestActivation:
    def test_activate_terminal_sets_online(self):
        t = make_terminal()
        t.send("ACTIVATE TERMINAL")
        assert t.is_online

    def test_activate_terminal_says_congratulations(self):
        t = make_terminal()
        response = t.send("ACTIVATE TERMINAL")
        assert "Congratulations" in response

    def test_terminal_id_in_activate_response(self):
        t = make_terminal("FINAL")
        response = t.send("ACTIVATE TERMINAL")
        assert "FINAL" in response

    def test_not_activated_by_partial_command_activate(self):
        t = make_terminal()
        t.send("ACTIVATE")
        assert not t.is_online

    def test_not_activated_by_partial_command_terminal(self):
        t = make_terminal()
        t.send("TERMINAL")
        assert not t.is_online

    def test_not_activated_by_lowercase(self):
        t = make_terminal()
        t.send("activate terminal")
        assert not t.is_online

    def test_not_activated_by_extra_spaces(self):
        t = make_terminal()
        t.send("ACTIVATE  TERMINAL")
        assert not t.is_online

    def test_not_activated_by_unknown_command(self):
        t = make_terminal()
        t.send("BOOT")
        assert not t.is_online

    def test_whitespace_trimmed(self):
        t = make_terminal()
        t.send("  ACTIVATE TERMINAL  ")
        assert t.is_online


class TestHelp:
    def test_help_shows_activate_command(self):
        t = make_terminal()
        assert "ACTIVATE TERMINAL" in t.send("HELP")

    def test_help_includes_terminal_id(self):
        t = make_terminal("MYSYS")
        assert "MYSYS" in t.send("HELP")


class TestUnknownCommands:
    def test_unknown_command_hints_at_help(self):
        t = make_terminal()
        response = t.send("WHAT")
        assert "HELP" in response

    def test_unknown_command_includes_bad_command(self):
        t = make_terminal()
        assert "BADCMD" in t.send("BADCMD")

    def test_unknown_command_includes_terminal_id(self):
        t = make_terminal("SYS99")
        assert "SYS99" in t.send("BADCMD")


class TestWelcome:
    def test_welcome_includes_terminal_id(self):
        t = make_terminal("SYS1")
        assert "SYS1" in t.get_welcome_message()

    def test_empty_payload_returns_welcome(self):
        t = make_terminal()
        response = t.send("")
        assert "MAIN" in response

    def test_empty_payload_does_not_activate(self):
        t = make_terminal()
        t.send("")
        assert not t.is_online


class TestState:
    def test_is_online_initially_false(self):
        assert not make_terminal().is_online

    def test_terminal_id_property(self):
        assert make_terminal("XYZ").terminal_id == "XYZ"

    def test_child_terminal_is_none(self):
        assert make_terminal().child_terminal is None

    def test_all_terminals_is_just_self(self):
        t = make_terminal()
        assert t.all_terminals() == [t]

    def test_seed_does_not_affect_behaviour(self):
        t1 = MainTerminal("X", seed=0)
        t2 = MainTerminal("X", seed=999)
        t1.send("ACTIVATE TERMINAL")
        t2.send("ACTIVATE TERMINAL")
        assert t1.is_online == t2.is_online

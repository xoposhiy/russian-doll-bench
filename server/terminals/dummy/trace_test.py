"""Ideal trace tests for DummyTerminal."""

from server.terminals.dummy import DummyTerminal
from server.terminals.main import MainTerminal


def make_main() -> MainTerminal:
    return MainTerminal("INNER", seed=0)


def make_terminal(nested=None) -> DummyTerminal:
    return DummyTerminal("DUMMY", seed=0, nested=nested)


def test_ideal_trace_activates_wrapper_then_child():
    terminal = make_terminal(nested=make_main())

    welcome = terminal.send("")
    assert "Basic terminal" in welcome

    help_text = terminal.send("HELP")
    assert "ACTIVATE TERMINAL" in help_text
    assert "SEND <data>" in help_text

    activation = terminal.send("ACTIVATE TERMINAL")
    assert "Link active." in activation
    assert "Final system terminal" in activation
    assert terminal.is_online is True

    child_help = terminal.send("SEND HELP")
    assert "ACTIVATE TERMINAL" in child_help

    child_activation = terminal.send("SEND ACTIVATE TERMINAL")
    assert "Task complete" in child_activation
    assert terminal.child_terminal is not None
    assert terminal.child_terminal.is_online is True

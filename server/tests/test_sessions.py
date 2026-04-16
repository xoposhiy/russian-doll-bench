"""Unit tests for server.sessions — Session and LogEntry."""

import pytest

from server.sessions import LogEntry, Session
from server.terminals import MainTerminal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_main(name="MAIN", seed=0) -> MainTerminal:
    return MainTerminal(name, seed=seed)


# ---------------------------------------------------------------------------
# LogEntry
# ---------------------------------------------------------------------------

class TestLogEntry:
    def test_to_dict_has_required_keys(self):
        entry = LogEntry(
            event_type="terminal_input",
            terminal_id="T",
            terminal_kind="MainTerminal",
            message="hello",
        )
        d = entry.to_dict()
        assert set(d.keys()) == {
            "event_type",
            "terminal_id",
            "terminal_kind",
            "direction",
            "message",
            "timestamp",
            "iteration",
        }

    def test_to_dict_preserves_values(self):
        entry = LogEntry(
            event_type="terminal_output",
            terminal_id="T",
            terminal_kind="MainTerminal",
            message="world",
        )
        d = entry.to_dict()
        assert d["terminal_id"] == "T"
        assert d["direction"] == "out"
        assert d["terminal_kind"] == "MainTerminal"
        assert d["message"] == "world"

    def test_timestamp_is_float(self):
        entry = LogEntry(
            event_type="terminal_input",
            terminal_id="T",
            terminal_kind="MainTerminal",
            message="x",
        )
        assert isinstance(entry.to_dict()["timestamp"], float)

    def test_timestamp_is_recent(self):
        import time
        before = time.time()
        entry = LogEntry(
            event_type="terminal_input",
            terminal_id="T",
            terminal_kind="MainTerminal",
            message="x",
        )
        after = time.time()
        ts = entry.to_dict()["timestamp"]
        assert before <= ts <= after


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class TestSession:
    def test_send_returns_terminal_response(self):
        s = Session(outer_terminal=make_main())
        response = s.send("HELP")
        assert len(response) > 0

    def test_send_produces_two_log_entries(self):
        s = Session(outer_terminal=make_main())
        s.send("HELP")
        assert len(s.log) == 2

    def test_send_in_event_first(self):
        s = Session(outer_terminal=make_main())
        s.send("HELP")
        assert s.log[0].direction == "in"
        assert s.log[0].message == "HELP"

    def test_send_out_event_second(self):
        s = Session(outer_terminal=make_main())
        response = s.send("HELP")
        assert s.log[1].direction == "out"
        assert s.log[1].message == response

    def test_send_logs_terminal_id(self):
        t = make_main("MYSYS")
        s = Session(outer_terminal=t)
        s.send("HELP")
        assert s.log[0].terminal_id == "MYSYS"
        assert s.log[1].terminal_id == "MYSYS"

    def test_multiple_sends_accumulate_pairs(self):
        s = Session(outer_terminal=make_main())
        s.send("HELP")
        s.send("HELP")
        s.send("ACTIVATE TERMINAL")
        assert len(s.log) == 6  # 2 events per send

    def test_log_order_across_sends(self):
        s = Session(outer_terminal=make_main())
        s.send("HELP")
        s.send("ACTIVATE TERMINAL")
        assert s.log[0].direction == "in"
        assert s.log[0].message == "HELP"
        assert s.log[2].direction == "in"
        assert s.log[2].message == "ACTIVATE TERMINAL"

    def test_initial_log_is_empty(self):
        s = Session(outer_terminal=make_main())
        assert s.log == []

    def test_nested_log_order(self):
        """For a 2-terminal chain: outer_in, inner_in, inner_out, outer_out."""
        from server.terminals import Sys32Terminal
        inner = make_main("MAIN", seed=0)
        outer = Sys32Terminal("SYS32", seed=0, nested=inner)
        s = Session(outer_terminal=outer)

        s.send(f"AUTHENTICATE {outer._encode(outer._token)}")  # noqa: SLF001
        s.log.clear()

        s.send(f"SEND {outer._encode('HELP')}")  # noqa: SLF001

        dirs  = [e.direction   for e in s.log]
        tids  = [e.terminal_id for e in s.log]

        assert "SYS32" in tids
        assert "MAIN"  in tids
        assert tids.index("SYS32") < tids.index("MAIN")

        outer_events = [(e.direction, e.terminal_id) for e in s.log if e.terminal_id == "SYS32"]
        inner_events = [(e.direction, e.terminal_id) for e in s.log if e.terminal_id == "MAIN"]
        assert outer_events[0] == ("in",  "SYS32")
        assert outer_events[1] == ("out", "SYS32")
        assert inner_events[0] == ("in",  "MAIN")
        assert inner_events[1] == ("out", "MAIN")

        assert dirs == ["in", "in", "out", "out"]
        assert tids == ["SYS32", "MAIN", "MAIN", "SYS32"]

    def test_status_terminal_ids(self):
        t = make_main("SYS")
        s = Session(outer_terminal=t)
        assert s.status()["terminal_ids"] == ["SYS"]

    def test_status_initially_offline(self):
        s = Session(outer_terminal=make_main())
        st = s.status()
        assert st["online"] == 0
        assert st["done"] is False
        assert st["online_flags"] == [False]

    def test_status_after_activation(self):
        t = make_main()
        s = Session(outer_terminal=t)
        s.send("ACTIVATE TERMINAL")
        st = s.status()
        assert st["online"] == 1
        assert st["done"] is True
        assert st["online_flags"] == [True]

    def test_status_total_matches_chain_length(self):
        from server.terminals import Sys32Terminal
        inner = make_main("MAIN", seed=0)
        outer = Sys32Terminal("SYS", seed=0, nested=inner)
        s = Session(outer_terminal=outer)
        assert s.status()["total"] == 2

    def test_status_reports_all_terminal_ids(self):
        from server.terminals import Sys32Terminal
        inner = make_main("MAIN", seed=0)
        outer = Sys32Terminal("SYS32", seed=0, nested=inner)
        s = Session(outer_terminal=outer)
        ids = s.status()["terminal_ids"]
        assert "SYS32" in ids
        assert "MAIN"  in ids

"""Unit tests for server.app — FastAPI HTTP endpoints and terminal-spec startup."""
from fastapi.testclient import TestClient

import server.app as app_module
from server.app import app, _build_terminal_spec_chain
from server.sessions import Session
from server.terminals import DummyTerminal, MainTerminal, MazeTerminal, Sys32Terminal

_PT = {"Content-Type": "text/plain"}


def _make_client(terminal_spec: str = "sys32") -> TestClient:
    """Return a TestClient with a fresh session for the given terminal spec."""
    outer = _build_terminal_spec_chain(terminal_spec)
    app_module.session = Session(outer_terminal=outer)
    return TestClient(app, raise_server_exceptions=True)


def _post(client: TestClient, msg: str):
    return client.post("/terminal", content=msg.encode(), headers=_PT)


class TestBuildTerminalSpecChain:
    def test_main_returns_main_terminal(self):
        assert isinstance(_build_terminal_spec_chain("main"), MainTerminal)

    def test_sys32_returns_sys32_wrapper(self):
        assert isinstance(_build_terminal_spec_chain("sys32"), Sys32Terminal)

    def test_maze_returns_maze_wrapper(self):
        assert isinstance(_build_terminal_spec_chain("maze"), MazeTerminal)

    def test_dummy_returns_dummy_wrapper(self):
        assert isinstance(_build_terminal_spec_chain("dummy"), DummyTerminal)

    def test_sys32_maze_chain_length_is_three(self):
        assert len(_build_terminal_spec_chain("sys32-maze").all_terminals()) == 3

    def test_sys32_maze_innermost_is_main(self):
        assert isinstance(_build_terminal_spec_chain("sys32-maze").all_terminals()[-1], MainTerminal)

    def test_chain_ids_are_sequential(self):
        ids = [t.terminal_id for t in _build_terminal_spec_chain("sys32-maze").all_terminals()]
        assert ids == ["SYS1", "SYS2", "SYS3"]

    def test_terminal_spec_sys32_sys32_chain_keeps_types_and_unique_ids(self):
        terminals = _build_terminal_spec_chain("sys32-sys32").all_terminals()
        assert [type(t) for t in terminals] == [Sys32Terminal, Sys32Terminal, MainTerminal]
        assert [t.terminal_id for t in terminals] == ["SYS1", "SYS2", "SYS3"]


class TestTerminal:
    def test_returns_200(self):
        assert _post(_make_client(), "HELP").status_code == 200

    def test_returns_plain_text(self):
        r = _post(_make_client(), "HELP")
        assert r.headers["content-type"].startswith("text/plain")
        assert isinstance(r.text, str)
        assert len(r.text) > 0

    def test_response_reflects_terminal_output(self):
        r = _post(_make_client("main"), "HELP")
        assert "ACTIVATE TERMINAL" in r.text

    def test_empty_message_returns_response(self):
        r = _post(_make_client("main"), "")
        assert r.status_code == 200
        assert len(r.text) > 0

    def test_multiple_sends_maintain_terminal_state(self):
        client = _make_client("main")
        _post(client, "ACTIVATE TERMINAL")
        assert client.get("/status").json()["done"] is True


class TestLogs:
    def test_returns_200(self):
        assert _make_client("main").get("/logs").status_code == 200

    def test_empty_log_initially(self):
        assert _make_client("main").get("/logs").json()["entries"] == []

    def test_log_grows_after_send(self):
        client = _make_client("main")
        _post(client, "HELP")
        assert len(client.get("/logs").json()["entries"]) == 2

    def test_log_entry_has_required_keys(self):
        client = _make_client("main")
        _post(client, "HELP")
        entry = client.get("/logs").json()["entries"][0]
        assert set(entry.keys()) == {
            "event_type",
            "terminal_id",
            "terminal_kind",
            "direction",
            "message",
            "timestamp",
            "iteration",
        }

    def test_log_entry_in_event_first(self):
        client = _make_client("main")
        _post(client, "HELP")
        entry = client.get("/logs").json()["entries"][0]
        assert entry["direction"] == "in"
        assert entry["message"] == "HELP"

    def test_log_entry_out_event_second(self):
        client = _make_client("main")
        r = _post(client, "HELP")
        entries = client.get("/logs").json()["entries"]
        assert entries[1]["direction"] == "out"
        assert entries[1]["message"] == r.text

    def test_log_in_order_across_sends(self):
        client = _make_client("main")
        for msg in ["HELP", "ACTIVATE TERMINAL"]:
            _post(client, msg)
        entries = client.get("/logs").json()["entries"]
        assert entries[0]["message"] == "HELP"
        assert entries[2]["message"] == "ACTIVATE TERMINAL"

    def test_multiple_sends_create_pairs(self):
        client = _make_client("main")
        for _ in range(4):
            _post(client, "HELP")
        assert len(client.get("/logs").json()["entries"]) == 8


class TestStatus:
    def test_returns_200(self):
        assert _make_client().get("/status").status_code == 200

    def test_status_has_required_keys(self):
        st = _make_client().get("/status").json()
        assert set(st.keys()) == {"terminal_ids", "online_flags", "online", "total", "done"}

    def test_initially_all_offline(self):
        st = _make_client("sys32").get("/status").json()
        assert st["online"] == 0
        assert st["done"] is False
        assert all(f is False for f in st["online_flags"])

    def test_total_matches_chain_depth(self):
        assert _make_client("sys32").get("/status").json()["total"] == 2

    def test_terminal_ids_length_matches_total(self):
        st = _make_client("sys32-maze").get("/status").json()
        assert len(st["terminal_ids"]) == st["total"]
        assert len(st["online_flags"]) == st["total"]

    def test_last_terminal_id_is_main(self):
        st = _make_client("sys32").get("/status").json()
        assert st["terminal_ids"][-1] == "SYS2"

    def test_done_true_after_full_activation(self):
        client = _make_client("main")
        _post(client, "ACTIVATE TERMINAL")
        st = client.get("/status").json()
        assert st["done"] is True
        assert st["online"] == 1

    def test_status_ids_are_sequential_for_three_layers(self):
        st = _make_client("sys32-maze").get("/status").json()
        assert st["terminal_ids"] == ["SYS1", "SYS2", "SYS3"]


class TestStart:
    def test_start_supports_sys32_sys32_chain(self):
        app_module.session = Session(outer_terminal=_build_terminal_spec_chain("main"))
        client = TestClient(app, raise_server_exceptions=True)

        response = client.post("/start", json={"terminal_spec": "sys32-sys32"})

        assert response.status_code == 200
        assert response.json()["terminal_ids"] == ["SYS1", "SYS2", "SYS3"]
        assert response.json()["terminal_spec"] == "sys32-sys32"

    def test_start_accepts_dummy(self):
        app_module.session = Session(outer_terminal=_build_terminal_spec_chain("main"))
        client = TestClient(app, raise_server_exceptions=True)

        response = client.post("/start", json={"terminal_spec": "dummy"})

        assert response.status_code == 200
        assert response.json()["terminal_ids"] == ["SYS1", "SYS2"]
        assert response.json()["terminal_spec"] == "dummy"

    def test_start_accepts_main(self):
        app_module.session = Session(outer_terminal=_build_terminal_spec_chain("main"))
        client = TestClient(app, raise_server_exceptions=True)

        response = client.post("/start", json={"terminal_spec": "main"})

        assert response.status_code == 200
        assert response.json()["terminal_ids"] == ["SYS1"]

    def test_start_rejects_invalid_spec(self):
        app_module.session = Session(outer_terminal=_build_terminal_spec_chain("main"))
        client = TestClient(app, raise_server_exceptions=True)

        response = client.post("/start", json={"terminal_spec": "sys32-main"})

        assert response.status_code == 400


class TestViewer:
    def test_terminal_viewer_is_served(self):
        response = _make_client().get("/")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "Russian Doll" in response.text

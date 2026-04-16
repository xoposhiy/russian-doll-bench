import random

from server.base_terminal import BaseTerminal
from server.terminals.main import MainTerminal
from server.terminals.maze import MazeTerminal
from server.terminals.maze.maze_terminal import (
    _collect_weighted_route_digits,
    _decode_hex_payload,
    _encode_plaintext,
    _grid_key_from_path,
    _solve_weighted_route,
)


SEED = 42


class EchoTerminal(BaseTerminal):
    def __init__(self, name: str, seed: int, nested=None) -> None:
        super().__init__(name=name, seed=seed, nested=None)

    def get_welcome_message(self) -> str:
        return f"[{self._terminal_id}] READY"

    def send(self, payload: str) -> str:
        return f"ECHO:{payload}"


def make_terminal(seed: int = SEED, nested=None) -> MazeTerminal:
    return MazeTerminal("MAZE", seed=seed, nested=nested)


def make_main() -> MainTerminal:
    return MainTerminal("INNER", seed=0)


def make_echo() -> EchoTerminal:
    return EchoTerminal("ECHO", seed=0)


def _activation_payload(terminal: MazeTerminal) -> str:
    return _encode_plaintext(terminal._activation_phrase, _grid_key_from_path(terminal._activation_map))  # noqa: SLF001


def _send_payload(terminal: MazeTerminal, plaintext: str) -> str:
    return _encode_plaintext(plaintext, _grid_key_from_path(terminal._send_map))  # noqa: SLF001


def test_weighted_route_digits_follow_min_cost_not_fewest_steps():
    grid = (
        "f11",
        "1f1",
        "111",
    )
    assert _collect_weighted_route_digits(grid) == ["f", "1", "1", "1", "1"]


def test_route_key_pads_last_nibble():
    key = _grid_key_from_path(("abc",))
    assert key == bytes.fromhex("abc0")


def test_codec_round_trip_works():
    key = bytes.fromhex("12ab")
    encoded = _encode_plaintext("PING", key)
    decoded, error = _decode_hex_payload(encoded, key)
    assert error == ""
    assert decoded == "PING"


def test_welcome_includes_both_maps_and_phrase():
    terminal = make_terminal()
    assert terminal.send("") == "Shortest path XOR Terminal is ready! Use HELP to get more info"

    response = terminal.send("MAP")
    assert "[MAZE] MAZE" in response
    assert "uplink: locked" in response
    assert "activation-phrase: " in response
    assert "activation-map #" in response
    assert "send-map #" in response


def test_help_mentions_costs_and_rotation_rules():
    response = make_terminal().send("HELP")
    assert "Maps show movement cost of every cell as a hex digit." in response
    assert "Every two nibbles from that route form one XOR-key byte." in response
    assert "Failed ACTIVATE rotates the activation terrain." in response
    assert "Successful SEND rotates the send terrain." in response


def test_activate_requires_hex_payload():
    response = make_terminal().send("ACTIVATE nope")
    assert "ACTIVATE failed: Expected hex bytes" in response


def test_failed_activate_rotates_only_activation_map():
    terminal = make_terminal()
    activation_before = terminal._activation_map  # noqa: SLF001
    send_before = terminal._send_map  # noqa: SLF001
    response = terminal.send("ACTIVATE 00")
    assert "Activation map rotated." in response
    assert terminal._activation_map != activation_before  # noqa: SLF001
    assert terminal._send_map == send_before  # noqa: SLF001


def test_correct_activate_unlocks_and_returns_encoded_child_welcome():
    terminal = make_terminal(nested=make_main())
    send_key = _grid_key_from_path(terminal._send_map)  # noqa: SLF001
    response = terminal.send(f"ACTIVATE {_activation_payload(terminal)}")
    assert "uplink: online" in response
    assert "status: UPLINK ONLINE" in response
    child_hex = response.split("uplink-response: ", 1)[1]
    decoded, error = _decode_hex_payload(child_hex, send_key)
    assert error == ""
    assert "[INNER] Final system terminal." in decoded


def test_send_is_blocked_before_activation():
    response = make_terminal(nested=make_echo()).send("SEND 00")
    assert "status: SEND blocked: uplink locked." in response


def test_successful_send_rotates_only_send_map():
    terminal = make_terminal(nested=make_echo())
    terminal.send(f"ACTIVATE {_activation_payload(terminal)}")
    activation_before = terminal._activation_map  # noqa: SLF001
    send_before = terminal._send_map  # noqa: SLF001
    response = terminal.send(f"SEND {_send_payload(terminal, 'PING')}")
    assert "status: SENT" in response
    assert terminal._activation_map == activation_before  # noqa: SLF001
    assert terminal._send_map != send_before  # noqa: SLF001


def test_send_response_is_encoded_with_pre_rotation_send_key():
    terminal = make_terminal(nested=make_echo())
    terminal.send(f"ACTIVATE {_activation_payload(terminal)}")
    key = _grid_key_from_path(terminal._send_map)  # noqa: SLF001
    response = terminal.send(f"SEND {_send_payload(terminal, 'PING')}")
    child_hex = response.split("uplink-response: ", 1)[1]
    decoded, error = _decode_hex_payload(child_hex, key)
    assert error == ""
    assert decoded == "ECHO:PING"


def test_same_seed_produces_same_initial_state():
    left = make_terminal(seed=17).send("MAP")
    right = make_terminal(seed=17).send("MAP")
    assert left == right


def test_map_dimensions_stay_fixed_across_rotations():
    terminal = make_terminal()
    initial_activation_rows = len(terminal._activation_map)  # noqa: SLF001
    initial_activation_cols = len(terminal._activation_map[0])  # noqa: SLF001
    initial_send_rows = len(terminal._send_map)  # noqa: SLF001
    initial_send_cols = len(terminal._send_map[0])  # noqa: SLF001

    terminal.send("ACTIVATE 00")
    terminal.send("ACTIVATE 00")

    assert len(terminal._activation_map) == initial_activation_rows  # noqa: SLF001
    assert len(terminal._activation_map[0]) == initial_activation_cols  # noqa: SLF001
    assert len(terminal._send_map) == initial_send_rows  # noqa: SLF001
    assert len(terminal._send_map[0]) == initial_send_cols  # noqa: SLF001


def _score_grid(grid: tuple[str, ...]) -> tuple[int, int]:
    _, moves = _solve_weighted_route(grid)
    return (1 if any(move in {"L", "U"} for move in moves) else 0, len(moves))


def _generate_candidates(seed: int, rows: int, cols: int, count: int = 10) -> list[tuple[str, ...]]:
    rng = random.Random(seed)
    return [
        tuple(
            "".join(rng.choice("0123456789abcdef") for _ in range(cols))
            for _ in range(rows)
        )
        for _ in range(count)
    ]


def test_generated_maps_pick_best_of_ten_candidates():
    terminal = make_terminal(seed=17)
    activation_rows = len(terminal._activation_map)  # noqa: SLF001
    activation_cols = len(terminal._activation_map[0])  # noqa: SLF001
    send_rows = len(terminal._send_map)  # noqa: SLF001
    send_cols = len(terminal._send_map[0])  # noqa: SLF001

    activation_candidates = _generate_candidates(17 ^ 0x1155AA, activation_rows, activation_cols)
    send_candidates = _generate_candidates(17 ^ 0x77CC44, send_rows, send_cols)

    assert terminal._activation_map == max(activation_candidates, key=_score_grid)  # noqa: SLF001
    assert terminal._send_map == max(send_candidates, key=_score_grid)  # noqa: SLF001

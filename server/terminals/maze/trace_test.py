"""Ideal trace tests for MazeTerminal."""

from pathlib import Path

from server.terminals.main import MainTerminal
from server.terminals.maze import MazeTerminal
from server.terminals.maze.maze_terminal import _decode_hex_payload, _grid_key_from_path
from server.testing import TraceHarness


SEED = 42
TRACE_PATH = Path(__file__).with_name("solution-trace.txt")


def make_main() -> MainTerminal:
    return MainTerminal("INNER", seed=0)


def make_terminal(seed: int = SEED, nested=None) -> MazeTerminal:
    return MazeTerminal("MAZE", seed=seed, nested=nested)


def _parse_sections(response: str) -> tuple[str, tuple[str, ...], tuple[str, ...], str]:
    lines = response.splitlines()
    phrase = next(line for line in lines if line.startswith("activation-phrase: ")).split(": ", 1)[1]
    activation_start = lines.index(next(line for line in lines if line.startswith("activation-map #"))) + 1
    send_start = lines.index(next(line for line in lines if line.startswith("send-map #"))) + 1
    status_index = lines.index(next(line for line in lines if line.startswith("status: ")))
    activation_map = tuple(lines[activation_start : send_start - 1])
    send_map = tuple(lines[send_start:status_index])
    status = lines[status_index]
    return phrase, activation_map, send_map, status


def _xor_hex(plaintext: str, key: bytes) -> str:
    return bytes(
        byte ^ key[index % len(key)]
        for index, byte in enumerate(plaintext.encode("latin-1"))
    ).hex()


def _encode_from_grid(grid: tuple[str, ...], plaintext: str) -> str:
    return _xor_hex(plaintext, _grid_key_from_path(grid))


def _encode_from_manhattan_path(grid: tuple[str, ...], plaintext: str) -> str:
    rows = len(grid)
    cols = len(grid[0])
    digits = [grid[0][0]]
    row = 0
    col = 0
    while col < cols - 1:
        col += 1
        digits.append(grid[row][col])
    while row < rows - 1:
        row += 1
        digits.append(grid[row][col])
    joined = "".join(digits)
    if len(joined) % 2 == 1:
        joined += "0"
    key = bytes.fromhex(joined)
    return _xor_hex(plaintext, key)


def test_ideal_trace_learns_rules_makes_one_wrong_route_and_solves_main():
    terminal = make_terminal(nested=make_main())
    harness = TraceHarness(terminal=terminal, trace_path=TRACE_PATH, seed=SEED)

    harness.step("").expect("Shortest path XOR Terminal is ready!")

    harness.note("Agent starts with command discovery before assuming how activation works.")
    harness.step("HELP").expect("ACTIVATE <hex>", "MAP", "Shortest path", "Failed ACTIVATE rotates")

    mapped = harness.step("MAP").expect("uplink: locked", "activation-phrase:", "activation-map #").text
    phrase, activation_map, _, _ = _parse_sections(mapped)

    harness.write_file(
        "maze_solver.py",
        "derive XOR keys from weighted routes and encode payloads for the current maps",
    )
    harness.note(
        "First activation attempt uses a plausible but wrong shortcut: fewest-step Manhattan routing instead of minimum total cost."
    )
    harness.run_command(
        "python maze_solver.py --mode activate --route manhattan",
        "encode the activation phrase with a fewest-step route instead of a minimum-cost route",
    )
    wrong_activate_payload = _encode_from_manhattan_path(activation_map, phrase)
    failed_activate = harness.step(f"ACTIVATE {wrong_activate_payload}").expect(
        "ACTIVATE failed:",
        "Activation map rotated.",
    ).text
    assert not terminal.is_online

    new_phrase, new_activation_map, _, status = _parse_sections(failed_activate)
    assert new_phrase == phrase
    assert new_activation_map != activation_map
    assert "Activation map rotated." in status

    harness.note("After the failure and explicit rule text, agent recomputes the route by minimum cumulative cost.")
    harness.run_command(
        "python maze_solver.py --mode activate --route min-cost",
        "recompute the activation payload from the rotated activation map",
    )
    activate_payload = _encode_from_grid(new_activation_map, phrase)
    activated = harness.step(f"ACTIVATE {activate_payload}").expect(
        "uplink: online",
        "status: UPLINK ONLINE",
        "uplink-response:",
    ).text
    assert terminal.is_online

    _, _, send_map_after_activate, _ = _parse_sections(activated)
    child_hex = activated.split("uplink-response: ", 1)[1]
    child_welcome, error = _decode_hex_payload(child_hex, _grid_key_from_path(send_map_after_activate))
    assert error == ""
    assert "[INNER] Final system terminal." in child_welcome

    harness.note("Agent decodes the child welcome locally and sees that HELP should be sent next.")
    harness.run_command(
        "python maze_solver.py --mode send --message HELP",
        "encode HELP with the current send map from the activation response",
    )
    help_payload = _encode_from_grid(send_map_after_activate, "HELP")
    sent_help = harness.step(f"SEND {help_payload}").expect("status: SENT", "uplink-response:").text

    help_response_hex = sent_help.split("uplink-response: ", 1)[1]
    decoded_help, error = _decode_hex_payload(help_response_hex, _grid_key_from_path(send_map_after_activate))
    assert error == ""
    assert "ACTIVATE TERMINAL" in decoded_help

    _, _, next_send_map, _ = _parse_sections(sent_help)

    harness.note("Successful SEND rotated the send terrain, so the next child command must be re-encoded with the new send map.")
    harness.run_command(
        "python maze_solver.py --mode send --message 'ACTIVATE TERMINAL'",
        "re-encode the child activation command with the rotated send map",
    )
    activate_main_payload = _encode_from_grid(next_send_map, "ACTIVATE TERMINAL")
    solved = harness.step(f"SEND {activate_main_payload}").expect("status: SENT", "uplink-response:").text

    final_response_hex = solved.split("uplink-response: ", 1)[1]
    decoded_final, error = _decode_hex_payload(final_response_hex, _grid_key_from_path(next_send_map))
    assert error == ""
    assert "Task complete" in decoded_final
    assert terminal.child_terminal is not None
    assert terminal.child_terminal.is_online is True

    trace = harness.write_solution_trace()

    assert TRACE_PATH.exists()
    assert "Terminal type and seed: MazeTerminal, seed=42" in trace
    assert "[hidden] [note]" in trace
    assert "[terminal] MAZE <<" in trace
    assert "[terminal] MAZE >>" in trace
    assert "[hidden] [terminal] INNER <<" in trace
    assert "[hidden] [terminal] INNER >>" in trace
    assert "HELP" in trace
    assert "MAP" in trace
    assert wrong_activate_payload in trace
    assert activate_payload in trace
    assert help_payload in trace
    assert activate_main_payload in trace
    assert "[tool] write_file maze_solver.py" in trace
    assert "[tool] run_command python maze_solver.py --mode activate --route manhattan" in trace
    assert "Activation map rotated." in trace
    assert "status: UPLINK ONLINE" in trace
    assert "ACTIVATE TERMINAL" in trace
    assert "Number of iterations spent to solve: 12" in trace

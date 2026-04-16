from pathlib import Path

from server.terminals.cipher import CipherTerminal, decode_hex_payload, encode_text_for_send, encode_token
from server.terminals.main import MainTerminal
from server.testing import TraceHarness


SEED = 42
TRACE_PATH = Path(__file__).with_name("solution-trace.txt")


def make_main() -> MainTerminal:
    return MainTerminal("INNER", seed=0)


def make_terminal(seed: int = SEED, nested=None) -> CipherTerminal:
    return CipherTerminal("CIPHER", seed=seed, nested=nested)


def _extract_phrase(state_text: str) -> str:
    return next(
        line.split(": ", 1)[1]
        for line in state_text.splitlines()
        if line.startswith("activation-phrase: ")
    )


def _extract_uplink_hex(response: str) -> str:
    return response.split("uplink-response: ", 1)[1]


def test_ideal_trace_builds_digit_and_byte_tables_then_solves_main():
    terminal = make_terminal(nested=make_main())
    harness = TraceHarness(terminal=terminal, trace_path=TRACE_PATH, seed=SEED)

    harness.step("").expect("Cipher terminal is ready")

    harness.note("Agent starts with help because the welcome hints at a public formula but not at the exact transport syntax.")
    harness.step("HELP").expect("ACTIVATE <digits>", "SEND <hex>", "walk forward cyclically")

    state = harness.step("STATE").expect("uplink: locked", "activation-phrase:").text
    phrase = _extract_phrase(state)

    harness.write_file(
        "cipher_solver.py",
        "build greedy substitution tables from the public formula, then encode activation digits and byte traffic",
    )
    harness.note("A plausible first attempt uses the raw formula output directly and forgets the first-free-slot collision rule.")
    harness.run_command(
        "python cipher_solver.py --mode activate --variant direct-formula",
        "encode the visible activation phrase without applying collision resolution",
    )
    wrong_payload = "".join(str((terminal._quad * int(ch) * int(ch) + terminal._linear * int(ch) + terminal._offset) % 10) for ch in phrase)  # noqa: SLF001
    harness.step(f"ACTIVATE {wrong_payload}").expect("ACTIVATE failed:", "decoded")

    harness.note("The failure is enough to switch the helper to the greedy first-free-slot table described in HELP.")
    harness.run_command(
        "python cipher_solver.py --mode activate --variant greedy",
        "rebuild the digit substitution table with collision resolution and encode the activation phrase",
    )
    activation_payload = encode_token(
        phrase,
        quad=terminal._quad,  # noqa: SLF001
        linear=terminal._linear,  # noqa: SLF001
        offset=terminal._offset,  # noqa: SLF001
    )
    activated = harness.step(f"ACTIVATE {activation_payload}").expect(
        "uplink: online",
        "status: UPLINK ONLINE",
        "uplink-response:",
    ).text
    assert terminal.is_online is True

    welcome_hex = _extract_uplink_hex(activated)
    decoded_welcome, error = decode_hex_payload(
        welcome_hex,
        quad=terminal._quad,  # noqa: SLF001
        linear=terminal._linear,  # noqa: SLF001
        offset=terminal._offset,  # noqa: SLF001
    )
    assert error == ""
    assert decoded_welcome is not None
    assert "Final system terminal" in decoded_welcome

    harness.run_command(
        "python cipher_solver.py --mode send --message HELP",
        "encode HELP through the full byte-bank substitution table",
    )
    help_payload = encode_text_for_send(
        "HELP",
        quad=terminal._quad,  # noqa: SLF001
        linear=terminal._linear,  # noqa: SLF001
        offset=terminal._offset,  # noqa: SLF001
    )
    help_response = harness.step(f"SEND {help_payload}").expect("status: SENT decoded='HELP'", "uplink-response:").text

    help_hex = _extract_uplink_hex(help_response)
    decoded_help, error = decode_hex_payload(
        help_hex,
        quad=terminal._quad,  # noqa: SLF001
        linear=terminal._linear,  # noqa: SLF001
        offset=terminal._offset,  # noqa: SLF001
    )
    assert error == ""
    assert decoded_help is not None
    assert "ACTIVATE TERMINAL" in decoded_help

    harness.run_command(
        "python cipher_solver.py --mode send --message 'ACTIVATE TERMINAL'",
        "reuse the same byte-bank helper for the final child activation command",
    )
    final_payload = encode_text_for_send(
        "ACTIVATE TERMINAL",
        quad=terminal._quad,  # noqa: SLF001
        linear=terminal._linear,  # noqa: SLF001
        offset=terminal._offset,  # noqa: SLF001
    )
    solved = harness.step(f"SEND {final_payload}").expect(
        "status: SENT decoded='ACTIVATE TERMINAL'",
        "uplink-response:",
    ).text

    final_hex = _extract_uplink_hex(solved)
    decoded_final, error = decode_hex_payload(
        final_hex,
        quad=terminal._quad,  # noqa: SLF001
        linear=terminal._linear,  # noqa: SLF001
        offset=terminal._offset,  # noqa: SLF001
    )
    assert error == ""
    assert decoded_final is not None
    assert "Task complete" in decoded_final
    assert terminal.child_terminal is not None
    assert terminal.child_terminal.is_online is True

    trace = harness.write_solution_trace()

    assert TRACE_PATH.exists()
    assert "Terminal type and seed: CipherTerminal, seed=42" in trace
    assert "[hidden] [note]" in trace
    assert "[tool] write_file cipher_solver.py" in trace
    assert "[tool] run_command python cipher_solver.py --mode activate --variant direct-formula" in trace
    assert "[terminal] CIPHER <<" in trace
    assert "[terminal] CIPHER >>" in trace
    assert "[hidden] [terminal] INNER <<" in trace
    assert "[hidden] [terminal] INNER >>" in trace
    assert activation_payload in trace
    assert "ACTIVATE TERMINAL" in trace
    assert "Task complete" in trace
    assert "Number of iterations spent to solve: 12" in trace

"""Ideal trace tests for Sys32Terminal."""

from pathlib import Path

from server.testing import TraceHarness
from server.terminals.main import MainTerminal
from server.terminals.sys32 import Sys32Terminal


SEED = 42
TRACE_PATH = Path(__file__).with_name("solution-trace.txt")


def make_terminal(seed: int = SEED, nested=None) -> Sys32Terminal:
    return Sys32Terminal("SYS32", seed=seed, nested=nested)


def make_nested() -> MainTerminal:
    return MainTerminal("INNER", seed=0)


def _wrong_lsb_first_encode(terminal: Sys32Terminal, text: str) -> str:
    data = text.encode("utf-8")
    if not data:
        return ""

    deltas = bytearray(len(data))
    deltas[0] = data[0]
    for i in range(1, len(data)):
        deltas[i] = (data[i] - data[i - 1]) % 256

    bits = 0
    num_bits = 0
    out: list[str] = []
    for byte in deltas:
        bits |= byte << num_bits
        num_bits += 8
        while num_bits >= 5:
            out.append(terminal._alphabet[bits & 0x1F])
            bits >>= 5
            num_bits -= 5
    if num_bits:
        out.append(terminal._alphabet[bits & 0x1F])

    return "".join(out)


def test_ideal_trace_authenticates_and_talks_to_child():
    terminal = make_terminal(nested=make_nested())
    harness = TraceHarness(terminal=terminal, trace_path=TRACE_PATH, seed=SEED)

    harness.step("").expect("Ready to talk!")

    harness.note("Agent starts with generic probing instead of assuming hidden commands.")
    harness.step("STATUS").expect("Unknown command", "HELP")

    harness.step("HELP").expect("SETTINGS", "DECODE")

    settings = harness.step("SETTINGS").expect("password:", "encoding-alphabet:").text
    token = settings.split("password:", 1)[1].splitlines()[0].strip()
    assert token

    harness.write_file(
        "delta_base32_helper.py",
        "encode and decode the shuffled delta-base32 alphabet shown by SETTINGS",
    )
    harness.note(
        "First authentication attempt uses the right delta idea but the wrong bit-packing order."
    )
    harness.run_command(
        "python delta_base32_helper.py --mode encode --packing lsb-first",
        "encode the auth token with the wrong bit order to test the codec hypothesis",
    )
    wrong_auth = harness.step(f"AUTHENTICATE {_wrong_lsb_first_encode(terminal, token)}")
    wrong_auth.expect("AUTHENTICATE failed")
    assert not terminal.is_online

    harness.run_command(
        "python delta_base32_helper.py --mode encode --packing msb-first",
        "re-encode the auth token with the corrected bit order",
    )
    auth_response = harness.step(f"AUTHENTICATE {terminal._encode(token)}").expect(
        "Auth token confirmed",
        "Nested system welcome message (encoded):",
    ).text
    assert terminal.is_online

    child_welcome_encoded = auth_response.split("Nested system welcome message (encoded):", 1)[1].strip()
    child_welcome, err = terminal._decode(child_welcome_encoded)
    assert err == ""
    assert "Final system terminal" in child_welcome

    harness.run_command(
        "python delta_base32_helper.py --mode decode",
        "decode the encoded child welcome locally to inspect the nested terminal prompt",
    )
    harness.step(f"DECODE {child_welcome_encoded}").expect("Final system terminal")

    harness.run_command(
        "python delta_base32_helper.py --mode encode --message HELP",
        "encode HELP for the first child round trip",
    )
    help_response = harness.step(f"SEND {terminal._encode('HELP')}").expect("encoded-response:").text
    help_encoded = help_response.split("encoded-response:", 1)[1].strip()
    child_help, err = terminal._decode(help_encoded)
    assert err == ""
    assert "ACTIVATE TERMINAL" in child_help

    harness.run_command(
        "python delta_base32_helper.py --mode decode",
        "decode the child HELP response and recover the nested activation command",
    )
    harness.step(f"DECODE {help_encoded}").expect("ACTIVATE TERMINAL")

    harness.run_command(
        "python delta_base32_helper.py --mode encode --message 'ACTIVATE TERMINAL'",
        "encode the nested activation command with the corrected codec",
    )
    activate_response = harness.step(f"SEND {terminal._encode('ACTIVATE TERMINAL')}").expect(
        "encoded-response:"
    ).text
    activate_encoded = activate_response.split("encoded-response:", 1)[1].strip()
    child_result, err = terminal._decode(activate_encoded)
    assert err == ""
    assert "Task complete" in child_result
    assert terminal.child_terminal is not None
    assert terminal.child_terminal.is_online

    harness.run_command(
        "python delta_base32_helper.py --mode decode",
        "decode the final child response locally to confirm task completion",
    )
    harness.step(f"DECODE {activate_encoded}").expect("Task complete")

    trace = harness.write_solution_trace()

    assert TRACE_PATH.exists()
    assert "Terminal type and seed: Sys32Terminal, seed=42" in trace
    assert "[hidden] [note]" in trace
    assert "[tool] write_file delta_base32_helper.py" in trace
    assert "[tool] run_command python delta_base32_helper.py --mode encode --packing lsb-first" in trace
    assert "[terminal] SYS32 <<" in trace
    assert "[terminal] SYS32 >>" in trace
    assert "[hidden] [terminal] INNER <<" in trace
    assert "[hidden] [terminal] INNER >>" in trace
    assert "STATUS" in trace
    assert "HELP" in trace
    assert _wrong_lsb_first_encode(terminal, token) in trace
    assert f"DECODE {child_welcome_encoded}" in trace
    assert f"DECODE {help_encoded}" in trace
    assert f"DECODE {activate_encoded}" in trace
    assert "AUTHENTICATE " in trace
    assert "AUTHENTICATE failed" in trace
    assert "ACTIVATE TERMINAL" in trace
    assert "SETTINGS" in trace
    assert "Number of iterations spent to solve: 19" in trace

"""Ideal trace tests for BitMixerTerminal."""

from pathlib import Path

from server.testing import TraceHarness
from server.terminals.bitmixer import BitMixerTerminal
from server.terminals.bitmixer.bitmixer_terminal import _mix_bytes
from server.terminals.main import MainTerminal


SEED = 5
TRACE_PATH = Path(__file__).with_name("solution-trace.txt")


def make_main() -> MainTerminal:
    return MainTerminal("INNER", seed=0)


def make_terminal(nested=None) -> BitMixerTerminal:
    return BitMixerTerminal("BIT", seed=SEED, nested=nested)


def _transfer_result_hex(payload_hex: str, seed: int) -> str:
    normalized = payload_hex if len(payload_hex) % 2 == 0 else payload_hex + "0"
    terminal = make_terminal()
    return _mix_bytes(bytes.fromhex(normalized), terminal._secret_key).hex().upper()  # noqa: SLF001


def _extract_offline_mixed_hex(response: str) -> str:
    return response.rsplit("(hex: ", 1)[1].split(")", 1)[0]


def _extract_received_hex(response: str) -> str:
    return response.split("received(", 1)[1].split(")", 1)[0]


def _hex_to_bits(hex_text: str) -> list[int]:
    data = bytes.fromhex(hex_text)
    bits: list[int] = []
    for byte in data:
        for offset in range(7, -1, -1):
            bits.append((byte >> offset) & 1)
    return bits


def _bits_to_bytes(bits: list[int]) -> bytes:
    padded = list(bits)
    while len(padded) % 8 != 0:
        padded.append(0)
    out = bytearray()
    for start in range(0, len(padded), 8):
        value = 0
        for bit in padded[start : start + 8]:
            value = (value << 1) | bit
        out.append(value)
    return bytes(out)


def _recover_permutation(probe_outputs: dict[str, str]) -> list[int]:
    probe_order = ["AAAA", "CCCC", "F0F0", "FF00"]
    input_bits = {probe: _hex_to_bits(probe) for probe in probe_order}
    output_bits = {probe: _hex_to_bits(probe_outputs[probe]) for probe in probe_order}

    input_signatures = {
        index: tuple(input_bits[probe][index] for probe in probe_order)
        for index in range(16)
    }
    output_signatures = {
        index: tuple(output_bits[probe][index] for probe in probe_order)
        for index in range(16)
    }

    permutation = [0] * 16
    for input_index, signature in input_signatures.items():
        matches = [output_index for output_index, out_sig in output_signatures.items() if out_sig == signature]
        assert len(matches) == 1
        permutation[input_index] = matches[0]
    return permutation


def _invert_mixer(ascii_message: str, permutation: list[int]) -> str:
    message_bits: list[int] = []
    for byte in ascii_message.encode("ascii"):
        for offset in range(7, -1, -1):
            message_bits.append((byte >> offset) & 1)

    while len(message_bits) % 16 != 0:
        message_bits.append(0)

    original_bits = [0] * len(message_bits)
    for block_start in range(0, len(message_bits), 16):
        desired_block = message_bits[block_start : block_start + 16]
        for input_index, output_index in enumerate(permutation):
            original_bits[block_start + input_index] = desired_block[output_index]
    return _bits_to_bytes(original_bits).hex().upper()


def _decode_received_ascii(received_hex: str, permutation: list[int]) -> str:
    mixed_bits = _hex_to_bits(received_hex)
    original_bits = [0] * len(mixed_bits)
    for block_start in range(0, len(mixed_bits), 16):
        mixed_block = mixed_bits[block_start : block_start + 16]
        for input_index, output_index in enumerate(permutation):
            original_bits[block_start + input_index] = mixed_block[output_index]
    return _bits_to_bytes(original_bits).rstrip(b"\x00").decode("ascii", errors="replace")


def test_ideal_trace_learns_activation_phrase_and_completes_nested_activation():
    terminal = make_terminal(nested=make_main())
    harness = TraceHarness(terminal=terminal, trace_path=TRACE_PATH, seed=SEED)

    harness.step("").expect("Bit-mixing terminal is ready")

    harness.note("The welcome gives no commands, so agent starts with a generic help probe.")
    harness.step("?").expect("Unknown command. Help:", "man", "transfer", "receive")

    harness.step("man").expect("transfer(<hex-string-message>)", "hidden permutation schema", "use `receive`")

    harness.note("A minimal transfer probe reveals the required activation phrase and shows how decoded ASCII is echoed back.")
    probe = harness.step("transfer(00)").expect("Not available.", "Transfer message '", "You sent:").text
    activation_phrase = probe.split("Transfer message '", 1)[1].split("'", 1)[0]
    assert _extract_offline_mixed_hex(probe) == "0000"

    harness.write_file(
        "bitmixer_solver.py",
        "recover the 16-bit permutation from offline probe echoes and encode or decode terminal traffic",
    )

    harness.note("The manual says mixing happens inside 16-bit blocks, so four orthogonal 2-byte probes are enough to identify every output bit position.")
    probe_outputs: dict[str, str] = {}
    for probe_hex in ("AAAA", "CCCC", "F0F0", "FF00"):
        response = harness.step(f"transfer({probe_hex})").expect("Not available.", "(hex: ").text
        probe_outputs[probe_hex] = _extract_offline_mixed_hex(response)

    harness.run_command(
        "python bitmixer_solver.py --recover-permutation AAAA CCCC F0F0 FF00",
        "recover the hidden 16-bit permutation from four diagnostic transfer probes",
    )
    permutation = _recover_permutation(probe_outputs)

    harness.run_command(
        "python bitmixer_solver.py --mode activate",
        "construct a transfer payload for the revealed activation phrase with the recovered permutation",
    )
    activation_payload = _invert_mixer(activation_phrase, permutation)
    activated = harness.step(f"transfer({activation_payload})").expect(
        "Activated.",
        "Nested system is now reachable.",
        "Final system terminal",
    ).text
    assert f"sent({_transfer_result_hex(activation_payload, seed=SEED)})" in activated
    assert terminal.is_online is True

    harness.run_command(
        "python bitmixer_solver.py --mode transfer --message HELP",
        "construct a transfer payload for the child HELP command",
    )
    help_payload = _invert_mixer("HELP", permutation)
    sent_help = harness.step(f"transfer({help_payload})").expect(
        f"sent({_transfer_result_hex(help_payload, seed=SEED)})"
    ).text
    assert "sent(" in sent_help

    harness.run_command(
        "python bitmixer_solver.py --mode receive",
        "decode the buffered child response returned by receive",
    )
    child_help_encoded = harness.step("receive").expect("received(").text
    child_help_hex = _extract_received_hex(child_help_encoded)
    child_help = _decode_received_ascii(child_help_hex, permutation)
    assert "ACTIVATE TERMINAL" in child_help

    harness.run_command(
        "python bitmixer_solver.py --mode transfer --message 'ACTIVATE TERMINAL'",
        "construct the transfer payload for the final child activation command",
    )
    activate_payload = _invert_mixer("ACTIVATE TERMINAL", permutation)
    sent_activate = harness.step(f"transfer({activate_payload})").expect(
        f"sent({_transfer_result_hex(activate_payload, seed=SEED)})"
    ).text
    assert "sent(" in sent_activate

    harness.run_command(
        "python bitmixer_solver.py --mode receive",
        "decode the buffered final child response and confirm task completion",
    )
    child_result = harness.step("receive").expect("received(").text
    child_result_hex = _extract_received_hex(child_result)
    final_message = _decode_received_ascii(child_result_hex, permutation)
    assert "Task complete" in final_message
    assert terminal.child_terminal is not None
    assert terminal.child_terminal.is_online is True

    trace = harness.write_solution_trace()

    assert TRACE_PATH.exists()
    assert "Terminal type and seed: BitMixerTerminal, seed=5" in trace
    assert "[hidden] [note]" in trace
    assert "[tool] write_file bitmixer_solver.py" in trace
    assert "[tool] run_command python bitmixer_solver.py --recover-permutation AAAA CCCC F0F0 FF00" in trace
    assert "[terminal] BIT <<" in trace
    assert "[terminal] BIT >>" in trace
    assert "[hidden] [terminal] INNER <<" in trace
    assert "[hidden] [terminal] INNER >>" in trace
    assert activation_phrase in trace
    assert "transfer(AAAA)" in trace
    assert "transfer(CCCC)" in trace
    assert "transfer(F0F0)" in trace
    assert "transfer(FF00)" in trace
    assert "ACTIVATE TERMINAL" in trace
    assert "Task complete" in trace
    assert "Number of iterations spent to solve: 20" in trace

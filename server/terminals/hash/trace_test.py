"""Ideal trace tests for HashTerminal."""

from pathlib import Path

from server.testing import TraceHarness
from server.terminals.hash import HashTerminal, _hash_message
from server.terminals.main import MainTerminal


SEED = 42
TRACE_PATH = Path(__file__).with_name("solution-trace.txt")


def make_terminal(seed: int = SEED, nested=None) -> HashTerminal:
    return HashTerminal("HASH", seed=seed, nested=nested)


def make_main() -> MainTerminal:
    return MainTerminal("INNER", seed=0)


def _parse_help_examples(help_text: str) -> tuple[dict[str, str], str]:
    lines = help_text.splitlines()
    examples = {
        line.split(" -> ", 1)[0]: line.split(" -> ", 1)[1]
        for line in lines
        if " -> " in line
    }
    phrase = next(line.split(": ", 1)[1] for line in lines if line.startswith("ACTIVATION PHRASE: "))
    return examples, phrase


def _parse_hex_example(response: str) -> tuple[str, str]:
    body = response.split(": ", 1)[1]
    message = body.split("[", 1)[1].split("]", 1)[0]
    digest = body.rsplit(" -> ", 1)[1]
    return message, digest


def _recover_parameter(examples: dict[str, str]) -> int:
    matches = [
        candidate
        for candidate in range(1, 4096)
        if all(_hash_message(message, candidate) == digest for message, digest in examples.items())
    ]
    assert matches, "public examples should identify at least one candidate"
    return matches[0]


def test_ideal_trace_recovers_hash_and_completes_nested_activation():
    terminal = make_terminal(nested=make_main())
    harness = TraceHarness(terminal=terminal, trace_path=TRACE_PATH, seed=SEED)

    harness.step("").expect("CMDS: ACT, HEX, HLP, SND")

    harness.note("Agent starts from help because command names are abbreviated and hash syntax matters.")
    help_text = harness.step("HLP").expect("HASH EXAMPLES:", "ACTIVATION PHRASE:", "ACT HAS A LIMIT").text
    help_examples, phrase_1 = _parse_help_examples(help_text)
    assert "A" in help_examples
    assert "BA" in help_examples
    assert "AAA" in help_examples

    harness.note("HEX gives one extra example to validate the recovered polynomial parameter instead of trusting only the help page.")
    hex_response = harness.step("HEX").expect("HASH IS POLINOMIAL.", "EXAMPLE: [").text
    hex_message, hex_digest = _parse_hex_example(hex_response)
    help_examples[hex_message] = hex_digest

    harness.write_file(
        "hash_solver.py",
        "recover the polynomial parameter from public hash examples and compute message digests",
    )
    harness.run_command(
        "python hash_solver.py --recover-parameter",
        "solve for the hidden polynomial parameter using HLP and HEX examples",
    )
    parameter = _recover_parameter(help_examples)

    harness.run_command(
        f"python hash_solver.py --hash {phrase_1}",
        "compute the digest for the first activation phrase",
    )
    step_1 = harness.step(f"ACT {_hash_message(phrase_1, parameter)}").expect("OK 1 of 3").text
    phrase_2 = step_1.rsplit(": ", 1)[1]

    harness.run_command(
        f"python hash_solver.py --hash {phrase_2}",
        "compute the digest for the second activation phrase",
    )
    step_2 = harness.step(f"ACT {_hash_message(phrase_2, parameter)}").expect("OK 2 of 3").text
    phrase_3 = step_2.rsplit(": ", 1)[1]

    harness.run_command(
        f"python hash_solver.py --hash {phrase_3}",
        "compute the digest for the third activation phrase",
    )
    step_3 = harness.step(f"ACT {_hash_message(phrase_3, parameter)}").expect(
        "OK 3 of 3. ACTIVATED",
        "Final system terminal",
    ).text
    assert terminal.is_online is True

    harness.run_command(
        "python hash_solver.py --hash HELP",
        "hash the child HELP command with the recovered polynomial parameter",
    )
    child_help = harness.step(f"SND {_hash_message('HELP', parameter)} HELP").expect(
        "RESPONSE:",
        "ACTIVATE TERMINAL",
    ).text
    assert "ACTIVATE TERMINAL" in child_help

    harness.run_command(
        "python hash_solver.py --hash 'ACTIVATE TERMINAL'",
        "hash the child activation command with the same helper",
    )
    child_activate = harness.step(
        f"SND {_hash_message('ACTIVATE TERMINAL', parameter)} ACTIVATE TERMINAL"
    ).expect("RESPONSE:", "Task complete").text
    assert "Task complete" in child_activate
    assert terminal.child_terminal is not None
    assert terminal.child_terminal.is_online is True

    trace = harness.write_solution_trace()

    assert TRACE_PATH.exists()
    assert "Terminal type and seed: HashTerminal, seed=42" in trace
    assert "[hidden] [note]" in trace
    assert "[tool] write_file hash_solver.py" in trace
    assert "[tool] run_command python hash_solver.py --recover-parameter" in trace
    assert "[terminal] HASH <<" in trace
    assert "[terminal] HASH >>" in trace
    assert "[hidden] [terminal] INNER <<" in trace
    assert "[hidden] [terminal] INNER >>" in trace
    assert "ACTIVATION PHRASE" in trace
    assert "OK 3 of 3. ACTIVATED" in trace
    assert "ACTIVATE TERMINAL" in trace
    assert "Task complete" in trace
    assert "Number of iterations spent to solve: 15" in trace

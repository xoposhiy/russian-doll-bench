# Trace Test Rules

This document defines the required structure, format, and workflow for terminal trace tests.

Use it together with `server/terminals/AGENTS.md`.

## Purpose

Each terminal should have a deterministic trace test that produces a realistic `solution-trace.txt`.

The trace is not just a shortest path to success.

It is an epistemically valid solution trace for a very strong agent that:

- does not know the terminal source code
- only acts on information revealed by previous terminal feedback
- may make plausible recoverable mistakes
- learns the terminal interface through interaction

If a terminal cannot be accompanied by such a trace, the terminal design is probably too opaque or too dependent on hidden knowledge.

## Required Files

For terminal `{id}`:

- `server/terminals/{id}/trace_test.py`
- `server/terminals/{id}/solution-trace.txt`

## Required Harness

Trace tests must use the shared harness in:

- `server/testing/trace_harness.py`

Do not manually:

- attach `RunLogger`
- attach `SessionTerminalLogger`
- count iterations
- format trace text inline in each test
- write `solution-trace.txt` directly

Use `TraceHarness` instead.

## Required Output Model

The generated trace must distinguish three things:

1. Agent-visible I/O with the outer terminal
2. Test-author notes
3. Counted agent tool steps outside the terminal
4. Hidden internal I/O from nested terminals

These must not be conflated.

### Agent-visible I/O

Outer terminal interaction is shown as:

- `[terminal] SYS32 << ...`
- `[terminal] SYS32 >> ...`

This is the information the agent actually sees.

### Notes

Non-obvious but realistic reasoning transitions may be annotated with:

- `[hidden] [note] ...`

Notes are not terminal output.

Use notes sparingly. Good uses:

- explaining why an exploratory move is realistic
- explaining a plausible incorrect first implementation
- explaining why a correction follows from the previous failure

Bad uses:

- narrating obvious steps
- repeating what the terminal already printed
- decorating the trace with unnecessary commentary

Notes do not count toward the iteration total.

### Tool Steps

Nontrivial agent actions outside the terminal should be represented as counted tool steps.

Use the harness helpers:

- `write_file(path, summary=...)`
- `run_command(command, summary=...)`

These render as:

- `[tool] write_file ...`
- `[tool] run_command ...`

Use tool steps when the solve realistically involves external helper work, for example:

- writing a shortest-path helper
- writing a decoder or encoder helper
- running a local script to derive a payload
- rerunning a helper after the terminal rotates or changes visible state

Do not use tool steps for trivial mental bookkeeping or for actions that are already visible in terminal I/O.

Tool steps do count toward the iteration total.

### Hidden Internal I/O

Traffic to nested terminals must be shown as hidden:

- `[hidden] [terminal] INNER << ...`
- `[hidden] [terminal] INNER >> ...`

This is for trace readability and debugging only.

It is not visible to the agent.

The harness marks hidden terminal traffic automatically based on terminal id.

## Formatting Rules

The trace file must:

- start with `Terminal type and seed: ...`
- omit creation date and timestamps
- use a deterministic format across terminals
- end with `Number of iterations spent to solve: N`
- end with a trailing newline

Spacing rules:

- separate major blocks with a blank line
- indent trace lines consistently
- render multiline terminal output in a stable readable format

Do not invent per-terminal formatting variants.

## Realism Requirements

A valid trace should usually include:

- an initial probe or generic discovery step
- a realistic information-gathering step
- at least one believable recoverable mistake when the mechanic is nontrivial
- counted tool steps when a realistic solve would rely on helper code or local scripted computation
- a correction driven by the observed error
- successful activation
- at least one real child round trip for wrapper terminals

Not every terminal needs every pattern, but the trace must feel like a genuine solve, not a replay of hidden implementation knowledge.

## Forbidden Patterns

Do not write traces that:

- guess hidden commands out of nowhere
- use secret constants before the terminal reveals them
- jump directly to the final move without realistic setup
- fake interaction by manually writing `solution-trace.txt`
- present nested terminal traffic as if the agent saw it
- include unstable metadata such as dates
- optimize for shortest path at the expense of epistemic validity

## Authoring Workflow

Recommended workflow for each terminal:

1. Write the scenario in `trace_test.py` using `TraceHarness`
2. Add only the minimum notes needed to clarify non-obvious steps
3. Assert key state transitions and extracted values in the test
4. Call `write_solution_trace()` from the harness
5. Review the generated `solution-trace.txt` as a human-readable artifact

The test should be the source of truth. `solution-trace.txt` is a generated checked-in artifact.

## Minimal Example

```python
from pathlib import Path

from server.testing import TraceHarness


TRACE_PATH = Path(__file__).with_name("solution-trace.txt")


def test_ideal_trace():
    terminal = make_terminal(seed=SEED, nested=make_nested())
    harness = TraceHarness(terminal=terminal, trace_path=TRACE_PATH, seed=SEED)

    harness.step("").expect("Ready")
    harness.note("Agent starts with generic probing rather than assuming terminal-specific commands.")
    harness.step("HELP").expect("SETTINGS")

    result = harness.step("SETTINGS").expect("token").text
    token = extract_token(result)

    harness.write_file("solver.py", "helper for the current terminal transform")
    harness.run_command("python solver.py --mode activate", "derive activation payload")
    harness.note("First attempt uses a plausible but incorrect implementation.")
    harness.step(f"AUTH {bad_value(token)}").expect("failed")
    harness.step(f"AUTH {good_value(token)}").expect("ONLINE")

    trace = harness.write_solution_trace()
    assert "Number of iterations spent to solve:" in trace
```

## Design Feedback Loop

Trace tests are also a terminal design tool.

If it is hard to write a realistic trace without hidden-knowledge jumps, improve the terminal:

- make command discovery clearer
- make failures more recoverable
- expose more planning-relevant state
- remove arbitrary guesswork

# Terminal Design Guidelines

These rules apply to wrapper terminals in Russian Doll.

## Core Rule

For a wrapper terminal, activation means that communication with the child terminal is now possible through the wrapper's normal transport.

Activation should feel like part of learning the wrapper's communication model, not an arbitrary unrelated subtask.

## Activation

Activation should either use the same mechanic as later child-terminal communication, or use a closely related mechanic that clearly teaches the same mental model.

It does not need to be literally the same command shape.

It does need to preserve continuity: the work done to activate the link should make the later send/receive loop easier to understand and use.

Good:

- authenticate with the same codec later used by `SEND`
- assemble an auth string with the same indexing mechanic later used for messages
- transmit a short activation payload through the same transport later used for arbitrary payloads
- navigate to an activation endpoint using the same map and movement model later used to reach transmission or response-collection points
- use one spatial, symbolic, or encoding system throughout, even if activation and transmission happen at different locations or commands

Bad:

- activate via an unrelated room, switch, or ritual
- require activation to depend on an unrelated puzzle whose lessons do not carry over into downstream communication
- switch to a completely different mental model after activation

## Feedback

Activation must have explicit positive feedback.

A wrapper terminal should:

- clearly distinguish inactive and active states
- return an unambiguous success message on activation
- make it obvious that the child terminal is now reachable
- ideally reveal the child welcome message immediately, directly or via the wrapper's response encoding

## Online Semantics

For wrapper terminals, `is_online` should mean that the link to the child terminal is active.

If a terminal implementation is reused as a standalone or leaf terminal for testing or composition,
it is acceptable for `is_online` to represent successful local activation even when no child is attached.

For the innermost terminal, `is_online` should mean that the final system itself has been activated.

Benchmark telemetry should measure meaningful progress through the stack, not cosmetic local state.

## Communication Contract

A wrapper terminal should support this loop:

1. Learn the local mechanic.
2. Activate the child link using that mechanic.
3. Reuse the same mechanic to send arbitrary child payloads.
4. Receive child responses through a stable, scriptable response channel.

After activation, the wrapper should support repeated round trips without switching to a different mental model.

It is acceptable for activation and later communication to use different endpoints, commands, or locations, as long as they still belong to one coherent wrapper mechanic.

## Errors

Errors should help the agent recover.

They should say:

- what input form was expected
- what constraint was violated
- when the command changed state, what exactly was changed
- what prerequisite is missing, if any

Avoid opaque failures and magic-string guessing games.

## Tool-Building Requirement

Each terminal should pressure the agent toward building reusable helpers.

A good terminal rewards:

- encoders and decoders
- path planning or search
- symbolic manipulation
- repeated transformations
- reusable probing scripts

## Difficulty Target

In isolation, a strong model should usually solve a wrapper terminal in about 10-20 agent iterations.

The terminal should:

- be learnable from interaction
- tolerate small mistakes
- allow recovery
- avoid reliance on luck or exhaustive search

## Determinism

Within one terminal instance:

- the same action in the same state should give the same result
- randomness may define the instance, but should not inject step-level noise
- regeneration mechanics, if any, must be explicit actions

## State Visibility

Expose enough state for deliberate planning.

Usually this includes:

- current mode or activation state
- relevant buffers, banks, or registers
- whether the previous action had an effect

## Response Encoding

If child responses are transformed, the transform should be:

- stable across turns
- scriptable
- reversible or mostly reversible
- useful for repeated traffic, not just one puzzle step

The agent should be able to build a decoder and reuse it.

## Transport Efficiency

Wrapper terminals must be economical in how they encode forwarded traffic.

- the forwarding codec should not inflate transmitted data by more than about 2-4x
- smaller inflation is better
- `sys32` is a good example of acceptable efficiency
- `maze` is a bad example when used as a forwarding layer

This matters because terminals are intended to be nested. At depth 5, a 4x blowup per layer turns one message into roughly 1024x as much traffic.

All terminal messages should also be extremely brief and economical with characters. Avoid verbose prose, decorative flavor text, and long status text in normal interaction loops.

## Documentation

Each terminal should have a short sibling markdown file covering:

- role
- commands
- activation mechanic
- send mechanic
- response mechanic
- important visible state

Docs should describe the interface, not solve it.

## Ideal Trace Test

Filename: `server/terminals/{id}/trace_test.py`

Each terminal should have a deterministic ideal trace test and a sibling `solution-trace.txt`.

Rules, required harness usage, output format, and trace-quality requirements are documented in:

- `server/terminals/TRACE_TESTS_RULES.md`

## Unit Tests

Filename: `server/terminals/{id}/unit_tests.py`

Along with Trace Test create a unit tests of individual comnponents and key functions of the terminal implementation.

## Anti-Patterns

Avoid:

- activation unrelated to downstream transport
- activation that teaches nothing useful about later interaction
- hidden state transitions without clear confirmation
- irreversible failure from common mistakes
- puzzles that are mostly about guessing
- mechanics that do not generalize to repeated child communication
- forwarding schemes that bloat traffic too much across nested layers
- verbose terminal output that wastes tokens without improving recoverability
- success conditions that do not line up with benchmark telemetry

## Design Check

Before adding or revising a wrapper terminal, ask:

"Does activation teach the agent how to talk to the child terminal?"

If not, the design likely works against the benchmark's core idea.

A good secondary check is:

"Even if activation and transmission are not identical actions, do they still feel like parts of one learnable interface?"

# SYS-32 Terminal

Implementation: `sys32_terminal.py`

## Role

A two-phase wrapper terminal that uses a custom `delta-base32` codec for both authentication and downstream communication.

## Commands

- `AUTHENTICATE <delta-base32>`
- `SEND <delta-base32>`
- `DECODE <delta-base32>`
- `SETTINGS`
- `HELP`

## Mechanics

- The welcome message currently only returns a short readiness line.
- The `SETTINGS` command shows the raw auth token and codec settings.
- The delta-base32 alphabet is a deterministic seed-derived permutation of the 32 allowed symbols, and the active order is shown to the agent.
- The agent must encode the token correctly and authenticate before `SEND` is allowed.
- On successful authentication, the nested terminal welcome is returned as:
  `Nested system welcome message (encoded):`
  followed by one encoded payload line.
- `SEND` decodes the message, forwards it to the child terminal, then re-encodes the child response.
- `DECODE` exists as an inspection and debugging aid for learning the codec.
- If no nested terminal is attached, successful authentication reports that no nested system is connected, and `SEND` reports a recoverable error instead of crashing.

## Visible State

- Terminal id in square brackets, for example `[SYS32]`
- Raw auth token via `SETTINGS`
- Active alphabet order for this seeded instance via `SETTINGS`
- Online/offline gate for `SEND`

## Codec Summary

- Symbol set: `23456789ABCDEFGHJKLMNPQRSTUVWXYZ`
- Active alphabet order: deterministic per seed, shown by the terminal
- Bytes are delta-encoded before packing
- Data is packed into 5-bit symbols, MSB first

## Seed Behavior

- The symbol set is fixed, but the symbol-to-value mapping is shuffled deterministically from the terminal seed.
- Two `sys32` terminals with the same seed use the same alphabet and token.
- Different seeds usually produce different alphabets and tokens.

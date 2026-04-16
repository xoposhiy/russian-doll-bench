# Maze Terminal

Implementation: `maze_terminal.py`

## Role

A two-phase wrapper terminal built around path planning on small weighted grids.

## Commands

- `ACTIVATE <hex>`
- `SEND <hex>`
- `MAP`
- `HELP`

## Encoding Logic

- The terminal exposes two seeded rectangular maps: one for activation and one for sending.
- Map size is chosen once from the terminal seed and stays fixed for the lifetime of that terminal instance.
- Different seeds can produce different fixed map sizes.
- The agent always starts conceptually at `(0,0)`.
- The target is always the bottom-right cell of the current map.
- Every cell shows one hex digit `0-9` or `a-f`.
- Movement is four-directional only: up, down, left, right.
- The effective route depends on cumulative entry cost, not just step count.
- Generated maps are filtered so the cheapest route is nontrivial: it must include at least one `L` or `U` move.
- Each map deterministically defines a multi-byte XOR key from the hex digits collected along the effective route.
- Route digits are grouped in order into byte pairs. If the route yields an odd number of hex digits, the final low nibble is padded with `0`.
- The activation map defines the activation XOR key stream.
- The send map defines the send XOR key stream.
- Payloads are supplied as hex bytes. The terminal XOR-decodes them with the relevant key stream before interpreting the plaintext.
- The activation map and send map evolve independently.
- The current send map stays stable until a successful `SEND`.
- After each successful `SEND`, only the send map regenerates and a new send key is computed for the next round.

## Activation Mechanic

- `ACTIVATE <hex>` XOR-decodes the payload with the activation key stream.
- The decoded plaintext must match the terminal's shown activation phrase exactly.
- On success, the child link becomes online and the child welcome message is immediately returned through the send/response codec.
- Before activation, `SEND` reports that the uplink is still locked.
- Activation does not regenerate the send map.
- Activation is persistent for the terminal instance: once the uplink is unlocked, later map regenerations do not require re-activation.
- If activation fails, the activation map regenerates immediately and the terminal shows the new activation map for the next attempt.
- The activation phrase stays fixed for the terminal instance; failed activation changes the map, not the phrase.

## Send Mechanic

- `SEND <hex>` is only available after activation.
- The payload is XOR-decoded with the send key stream and forwarded to the child terminal as plain text.
- This reuses the same local idea as activation: derive the correct key stream for the current send map, then encode traffic with it, but without repeating the activation gate.
- After the child response is produced, the terminal rotates to a fresh send map before the next command round.
- The successful `SEND` output should immediately include the newly generated send map and current uplink state, so the agent can plan the next route without issuing `MAP`.
- The agent must therefore solve a new shortest-path instance for every successful downstream send.

## Response Mechanic

- Child responses are XOR-encoded with the same send key stream and returned as lowercase hex.
- The wrapper does not change the response bytes beyond XOR and hex encoding.
- If no child terminal is attached, activation can still succeed locally, and `SEND` returns a short recoverable offline message.
- The encoded response is still based on the pre-rotation send key stream; regeneration happens only after that response is emitted.
- The post-send map refresh is part of the same terminal response, appended after the encoded child payload.

## Welcome Message

- Empty input returns the short line `Shortest path XOR Terminal is ready!`.
- `MAP` prints the full visible state snapshot.
- The state snapshot shows the terminal id, uplink status as `uplink: locked|online`, the `activation-phrase`, the current activation map, the current send map, and the current status line.
- Child payloads in successful `ACTIVATE` and `SEND` responses are shown as lowercase hex in `uplink-response: <hex>`.
- The activation phrase is short and seed-derived.
- After each failed `ACTIVATE`, the terminal should emit the refreshed activation map.
- After each successful `SEND`, the terminal should emit the refreshed send map, preserving the already-unlocked online state.
- `MAP` should reprint the current activation map, current send map, activation phrase, and online state without changing any state.

## Learning the mechanics

- `HELP` explicitly states that maps show per-cell movement costs, that the shortest path from top-left to bottom-right defines the XOR key, and that every two steps define one byte of that key.
- `HELP` also states that failed activation rotates the activation terrain and successful sends rotate the send terrain.
- Errors should expose enough structure to learn from probing, especially for invalid hex, wrong decoded activation text, and locked send before activation.
- The design should reward building a small shortest-path helper and a reusable XOR/hex helper, then reusing them across repeated map regenerations.

## Seed Behavior

- Activation-map size, send-map size, cell costs, activation phrase, and regeneration order are deterministic from the terminal seed.
- The terminal should derive deterministic sequences for the activation maps and send maps rather than one fixed map.
- Within one terminal instance, all regenerated activation and send maps keep the same dimensions.
- Two `maze` terminals with the same seed must produce the same activation-map sequence, send-map sequence, phrases, and key streams.
- Different seeds should usually change both map sequences and the resulting path-derived key streams.

# Cipher Terminal

Implementation: `cipher_terminal.py`

## Role

A substitution-cipher wrapper terminal that derives a seeded symbol mapping from a public hash formula.

## Commands

- `ACTIVATE <digits>`
- `SEND <hex>`
- `STATE`
- `HELP`

## Mapping Logic

- One public quadratic score formula is shown by the terminal.
- The same formula shape is used twice:
  - activation on the digit bank `0..9`
  - transport on the byte bank `0..255`
- The terminal does not use the raw formula output as a direct substitution table.
- Instead, it fills the cipher table left-to-right by source code:
  - score the current source code
  - if that destination slot is free, claim it
  - otherwise walk forward cyclically until the first free slot appears
- This produces a deterministic one-to-one substitution table for the chosen bank.
- The digit-bank table and byte-bank table are therefore related, but not identical, because the bank sizes differ.

## Activation Mechanic

- `ACTIVATE <digits>` expects a digit string encoded through the digit-bank substitution table.
- The visible activation phrase is plain digits.
- The terminal decodes the supplied ciphertext through the digit-bank table and compares the result with the shown phrase.
- On success, the uplink becomes online and the child welcome message is immediately returned through the byte-bank transport codec.
- Failed activation keeps the same visible state and reports the decoded candidate.

## Send Mechanic

- `SEND <hex>` is available only after activation.
- The payload is interpreted as hex bytes.
- Those bytes are decoded through the byte-bank substitution table, converted to Latin-1 text, and forwarded to the child terminal.
- This reuses the same learned substitution mechanic as activation, only on the full byte bank.

## Response Mechanic

- Child responses are encoded with the byte-bank substitution table and returned as lowercase hex.
- The wrapper keeps one stable mapping for the whole terminal instance.
- If no child terminal is attached, activation can still succeed locally and later `SEND` returns a short recoverable offline response.

## Visible State

- `STATE` prints:
  - terminal id
  - uplink status
  - activation phrase
  - formula coefficients
  - a short reminder of which bank each command uses
  - the latest status line
- Successful `ACTIVATE` and `SEND` responses also include `uplink-response: <hex>`.

## Learning The Mechanic

- `HELP` reveals the command syntax, the public formula, and that collisions advance to the next free slot cyclically.
- The interface intentionally leaves the agent to build the actual table and its inverse locally.
- The design should reward writing one reusable helper that can:
  - generate both bank tables
  - invert them
  - encode digit activation payloads
  - encode and decode byte traffic for repeated child communication

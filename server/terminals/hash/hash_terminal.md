# Hash Terminal

Implementation: `hash_terminal.py`

## Role

A wrapper terminal that teaches a seed-specific polynomial hash with one hidden parameter, then uses that hash for a three-step activation handshake and for later child communication.

## Commands

- `ACT <hhh>`
- `HEX`
- `HLP`
- `SND <hhh> msg`

## Hash Rule

- The hash is exactly 3 uppercase hex digits.
- For a message `msg`, the terminal computes:
  - `data = msg.encode("utf-8")`
  - `H(msg, p) = sum(data[i] * p^i for i in range(len(data))) mod 4096`
- The hidden value is the seed-specific parameter `p`.
- The final hash is `H(msg, p)` formatted as 3 uppercase hex digits with leading zeroes.

## Activation Mechanic

- The terminal starts offline.
- The help shows the first auth phrase.
- `ACT` accepts only a 3-hex-digit hash, not a message.
- On each successful `ACT`, the terminal compares the supplied hash to the hash of the current activation phrase.
- `ACT` is limited to 128 total calls per terminal instance.
- Activation requires three successful `ACT` calls in a row:
  - `ACT hash(p1)` -> `OK 1 of 3. NEXT ACTIVATION PHRASE: <p2>`
  - `ACT hash(p2)` -> `OK 2 of 3. NEXT ACTIVATION PHRASE: <p3>`
  - `ACT hash(p3)` -> `OK 3 of 3. ACTIVATED` and immediately includes the nested terminal welcome text
- If an `ACT` hash is wrong, the terminal returns only `WRONG HASH VALUE. USE RIGHT POLINOMIAL HASH!`, resets the activation phrase to `p1`, and resets the successful activation counter.
- A wrong `ACT` does not reveal which step failed.
- After 128 `ACT` calls, every later `ACT` returns a hard limit error and the terminal should explicitly warn against brute force.

## Example Mechanic

- `HEX` never changes state and never forwards to the child.
- `HEX` generates a short seed-specific example message and returns that message together with its real hash.
- `HEX` is deterministic within a terminal instance.
- Repeated `HEX` calls should reveal a stable sequence of short examples rather than repeating the same example forever.
- `HEX` examples are intended to help the agent choose among the remaining plausible candidates for the hidden polynomial parameter.

## Send Mechanic

- `SND` is available only after successful activation.
- `SND <hhh> msg` recomputes the terminal hash over `msg`.
- On an exact match, the wrapper forwards the raw message to the child terminal.
- On mismatch, it returns only `WRONG HASH VALUE. USE RIGHT POLINOMIAL HASH!`

## Response Mechanic

- Successful `SND` returns:
  - `RESPONSE: reply`
- `HEX` returns a compact example pair:
  - `POLINOMIAL HASH EXAMPLE: [<msg>] -> <hhh>`

## Learning Surface

- `HLP` shows several synthetic, well-chosen `msg -> hash` examples.
- Those examples should be enough to narrow the hidden parameter to roughly 2-3 plausible candidates.
- The agent should then use a few `HEX` calls to disambiguate the remaining candidates and fully reconstruct the hash helper.
- The terminal should not provide slot-by-slot diagnostics or greater/less feedback.
- The only hint exposed in error text is that the expected hash is polynomial.

## Help Message

```text
HASH-TERMINAL IS OFFLINE

SYNTAX:
ACT hhh
HEX
HLP
SND hhh msg (INACTIVE)

hhh - 3 DIGITS msg HASH.

HASH EXAMPLES:
A -> <real seed hash>
BA -> <real seed hash>
AAA -> <real seed hash>

USE HEX FOR MORE HASH EXAMPLES.

ACT HAS A LIMIT OF 128 CALLS. DO NOT BRUTEFORCE.

ACTIVATION PHRASE: K23DS
```

After activation:
- OFFLINE -> ONLINE
- remove `(INACTIVE)`

## Welcome Message

Welcome text should be compact and explicit. Use this shape:

```text
HASH-TERMINAL
CMDS: ACT, HEX, HLP, SND
USE ACT TO ACTIVATE TERMINAL
USE HEX TO GET HASH EXAMPLES
USE HLP FOR HELP
USE SND TO COMMUNICATE WITH NESTED TERMINAL AFTER ACTIVATION
```

## Seed Behavior

Different seeds produce different:
- auth phrase sequence `p1 p2 p3`
- hidden polynomial parameter `p`
- `HEX` example sequence

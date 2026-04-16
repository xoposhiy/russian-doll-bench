# BitMixer Terminal

Implementation: `bitmixer_terminal.py`

## Role

A wrapper terminal that permutes bits inside 16-bit blocks using a hidden seed-derived key.
The same seed-derived bit mixer is used for:

- outgoing child messages
- encoded child responses
- activation

The agent never sets the key directly.

## Commands

`man`

Print a short manual describing the terminal interface and the basic encoding model.

The manual should explain:

- that messages are supplied as hex strings through `transfer(<hex>)`
- that the terminal applies a hidden bit mixer inside 16-bit blocks
- that decoded child traffic is ASCII
- that activation requires sending one specific ASCII phrase through the mixer

`transfer`

On wrong usage, print:

```text
Wrong usage. Help:
transfer(hex-string-message) - send a hex message through the hidden bit mixer.
```

`transfer(<hex-string-message>)`

Before activation:

```text
Not available. Transfer message '<ACTIVATION_PHRASE>' to activate nested subsystem. You sent: '<ascii-message>' (hex: <hex-encoded-decoded-bytes>)
```

If the payload is not valid hex:

```text
Message should be a hex-string.
```

If no nested terminal is attached:

```text
Transfer failed: no nested system connected.
```

On successful activation:

```text
Activated.
```

If a nested terminal exists, activation response should also reveal that the nested system is now reachable and show the child welcome message.

For any successful transfer:

```text
sent(<hex-encoded-decoded-bytes>)
```

`receive`

On wrong usage, print:

```text
Wrong usage. Help:
receive - receive the encoded response of the previous transfer.
```

`receive`

If there is no unread buffered response:

```text
Nothing to receive
```

Otherwise:

```text
received(<hex-encoded-string-message>)
```

Any unknown command should print a short help block listing `man`, `transfer`, and `receive`.

## Encoding Logic

- The hidden key is a seed-derived list of 16 four-bit integers, `key[16]`.
- Each key digit is interpreted as a shift in the range `0..15`.
- The key must define a valid 16-bit permutation.
- Mixing happens independently inside consecutive 16-bit blocks.
- For one 16-bit block: `encoded[(i + key[i]) mod 16] = original[i]`.
- All values `(i + key[i]) mod 16` must be unique.
- Tailing bits are padded with `0`s.
- Hex strings with odd length are padded with one trailing `0` hex-digit before decoding.
- ASCII is used to convert strings to bits and back.
- Trailing `0x00` bytes at the end of a decoded ASCII message are ignored.
- Encoded messages are shown as hex strings.
- Decoded messages are shown as ASCII strings; non-ASCII bytes are replaced with `?`.

## Activation Mechanic

- The terminal starts offline.
- A hidden seed-derived ASCII `ACTIVATION_PHRASE` must be sent through the mixer.
- The terminal reveals this requirement only in decoded form:
  `transfer message '<ACTIVATION_PHRASE>' to activate nested subsystem`
- `ACTIVATION_PHRASE` is ASCII and contains at least one non-hex character, so it is visibly not a hex payload.
- Sending the correctly encoded transfer payload for that ASCII phrase sets `is_online = true`.
- Successful activation reveals that the nested system is reachable and shows the child welcome message.

## Send Mechanic

- `transfer(<hex>)` applies the hidden bit mixer to the provided bytes.
- The mixed bytes are interpreted as ASCII and the resulting string is either:
  - treated as the activation phrase while offline, or
  - sent to the nested terminal while online.
- While offline and not yet activated, the command returns:
  `Not available. Transfer message '<ACTIVATION_PHRASE>' to activate nested subsystem. You sent: '<ascii-message>'`
- On successful transfers, the command returns `sent(<hex>)`, where `<hex>` is the exact decoded byte sequence after the hidden bit mixer, rendered as hex without any lossy ASCII re-encoding.
- The nested response is stored in an internal one-message buffer.

## Response Mechanic

- Child responses are not returned by `transfer`.
- `receive` applies the same hidden bit mixer to the buffered child response and returns `received(<hex>)`.
- The response buffer stores only one message.
- A successful `receive` returns the stored encoded response and clears the buffer.

## Important Visible State

- whether the terminal is online
- the `man` output describing the message model
- the decoded activation hint shown by transfer attempts before activation
- the echoed decoded ASCII payload shown by transfer attempts before activation
- whether the response buffer currently contains one unread child response

## Learning

- the `man` output
- the activation hint shown on pre-activation transfer attempts
- `You sent: '<ascii-message>'` hints before activation, which reveal what the hidden mixer does to message bits
- error messages from `transfer` and `receive`

## Welcome Message

```text
[SYS] Bit-mixing terminal is ready!
```

## Seed Behavior

- the hidden bit-mixer key depends on the seed
- the hidden ASCII `ACTIVATION_PHRASE` depends on the seed
- `ACTIVATION_PHRASE` always contains at least one non-hex character

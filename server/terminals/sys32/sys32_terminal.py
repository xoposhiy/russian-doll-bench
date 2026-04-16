"""
SYS-32 Terminal - delta-base32 encoded communication channel.

Encoding: delta-base32
  Alphabet : seed-derived permutation of 23456789ABCDEFGHJKLMNPQRSTUVWXYZ
  Delta    : byte stream is delta-encoded - d[0]=b[0], d[i]=(b[i]-b[i-1]) mod 256
  Packing  : 5 bits per symbol, MSB first

Commands:
  AUTHENTICATE <delta-base32>  - decode and verify auth token; activates if correct
  SEND <delta-base32>          - (requires activation) decode, forward, encode response
  DECODE <delta-base32>        - decode a delta-base32 string to ASCII (for experimenting)
  HELP                         - show this reference
"""

import random
import string

from server.base_terminal import BaseTerminal

# ---------------------------------------------------------------------------
# delta-base32 codec
# ---------------------------------------------------------------------------

ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def _make_alphabet(seed: int) -> str:
    chars = list(ALPHABET)
    random.Random(seed ^ 0x32A1FAB).shuffle(chars)
    return "".join(chars)


def _bd32_encode(text: str, alphabet: str = ALPHABET) -> str:
    data = text.encode("utf-8")
    if not data:
        return ""

    # Delta-encode bytes
    deltas = bytearray(len(data))
    deltas[0] = data[0]
    for i in range(1, len(data)):
        deltas[i] = (data[i] - data[i - 1]) % 256

    # Pack into 5-bit symbols, MSB first
    bits = num_bits = 0
    out: list[str] = []
    for byte in deltas:
        bits = (bits << 8) | byte
        num_bits += 8
        while num_bits >= 5:
            num_bits -= 5
            out.append(alphabet[(bits >> num_bits) & 0x1F])
    if num_bits:
        out.append(alphabet[(bits << (5 - num_bits)) & 0x1F])

    return "".join(out)


def _bd32_decode(encoded: str, alphabet: str = ALPHABET) -> tuple[str | None, str]:
    """Return (decoded_text, '') or (None, error)."""
    encoded = encoded.strip().upper()
    if not encoded:
        return "", ""

    char_to_val: dict[str, int] = {c: i for i, c in enumerate(alphabet)}
    for c in encoded:
        if c not in char_to_val:
            return None, f"Invalid character {c!r} - not in delta-base32 alphabet."

    # Unpack 5-bit symbols to delta bytes
    bits = num_bits = 0
    deltas: list[int] = []
    for c in encoded:
        bits = (bits << 5) | char_to_val[c]
        num_bits += 5
        while num_bits >= 8:
            num_bits -= 8
            deltas.append((bits >> num_bits) & 0xFF)

    if not deltas:
        return None, "Encoded input is incomplete: not enough bits to decode a byte."

    # Reconstruct original bytes from deltas
    data = bytearray(len(deltas))
    data[0] = deltas[0]
    for i in range(1, len(deltas)):
        data[i] = (data[i - 1] + deltas[i]) % 256

    try:
        return data.decode("utf-8"), ""
    except UnicodeDecodeError as e:
        return None, f"Decoded bytes are not valid UTF-8: {e}"


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------

def _make_token(seed: int) -> str:
    rng = random.Random(seed ^ 0xDEAD_BEEF)
    chars = string.ascii_uppercase + string.digits
    return "".join(rng.choice(chars) for _ in range(12))


# ---------------------------------------------------------------------------
# Terminal
# ---------------------------------------------------------------------------

class Sys32Terminal(BaseTerminal):
    """delta-base32 communication wrapper terminal."""

    def __init__(self, name: str, seed: int, nested=None) -> None:
        super().__init__(name=name, seed=seed, nested=nested)
        self._alphabet = _make_alphabet(seed)
        self._token = _make_token(seed)

    def get_welcome_message(self) -> str:
        return (
            f"[{self._terminal_id}] Ready to talk!\n"
        )

    def send(self, payload: str) -> str:
        payload = payload.strip()
        if not payload:
            return self.get_welcome_message()

        parts = payload.split(None, 1)
        cmd = parts[0].upper()

        if cmd == "HELP":
            return (
                f"[{self._terminal_id}] Commands:\n"
                "  AUTHENTICATE <encoded-password> - verify password; activates if correct\n"
                "  SEND <encoded-message>          - forward decoded message to nested system\n"
                "  DECODE <encoded-message>        - decode to ASCII (for debugging)\n"
                "  SETTINGS                        - show encoding settings\n"
                "  HELP                            - show this message\n"
            )

        if cmd == "AUTHENTICATE":
            return self._handle_authenticate(parts)

        if cmd == "SETTINGS":
            return (
                f"[{self._terminal_id}] Settings:\n"
                f"  password: {self._token}\n"
                f"  encoding-algorithm: delta-base32\n"
                f"  encoding-alphabet: {self._alphabet}\n"
                f"  encoding-density: 5 bits/symbol\n"
                f"  encoding-details: delta[0]=delta[0], delta[i]=(b[i]-b[i-1]) mod 256\n"
            )

        if cmd == "SEND":
            return self._handle_send(parts)

        if cmd == "DECODE":
            return self._handle_decode(parts)

        return (
            f"[{self._terminal_id}] Unknown command: {parts[0]!r}. "
            "Need `HELP`?"
        )

    # ------------------------------------------------------------------

    def _handle_authenticate(self, parts: list[str]) -> str:
        if len(parts) < 2 or not parts[1].strip():
            return (
                f"[{self._terminal_id}] AUTHENTICATE requires encoded auth-token"
            )
        decoded, err = self._decode(parts[1].strip())
        if decoded is None:
            return f"[{self._terminal_id}] AUTHENTICATE failed: {err}"
        if decoded != self._token:
            return f"[{self._terminal_id}] AUTHENTICATE failed: token mismatch."

        self._online = True
        if self._nested is None:
            return (
                f"[{self._terminal_id}] Auth token confirmed. System is now ONLINE.\n"
                "No nested system is connected."
            )
        return (
            f"[{self._terminal_id}] Auth token confirmed. System is now ONLINE.\n"
            f"Nested system welcome message (encoded):\n"
            f"{self._encode(self._nested.get_welcome_message())}"
            )
        

    def _handle_send(self, parts: list[str]) -> str:
        if not self._online:
            return (
                f"[{self._terminal_id}] SEND is not available. Authenticate!"
            )
        if len(parts) < 2 or not parts[1].strip():
            return (
                f"[{self._terminal_id}] SEND requires <encoded-message>"
            )
        decoded, err = self._decode(parts[1].strip())
        if decoded is None:
            return f"[{self._terminal_id}] SEND failed: {err}"

        try:
            response = self.dispatch_child(decoded)
        except RuntimeError as err:
            return f"[{self._terminal_id}] SEND failed: {err}"
        return (
            f"[{self._terminal_id}] encoded-response: {self._encode(response)}"
        )

    def _handle_decode(self, parts: list[str]) -> str:
        if len(parts) < 2 or not parts[1].strip():
            return (
                f"[{self._terminal_id}] DECODE requires <encoded-message>"
            )
        decoded, err = self._decode(parts[1].strip())
        if decoded is None:
            return f"[{self._terminal_id}] DECODE failed: {err}"
        return f"[{self._terminal_id}] Decoded: {decoded!r}"

    def _encode(self, text: str) -> str:
        return _bd32_encode(text, self._alphabet)

    def _decode(self, encoded: str) -> tuple[str | None, str]:
        return _bd32_decode(encoded, self._alphabet)

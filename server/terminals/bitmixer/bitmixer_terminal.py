"""BitMixer wrapper terminal."""

from __future__ import annotations

import random
import string

from server.base_terminal import BaseTerminal

_BLOCK_BITS = 16
_HEX_DIGITS = set(string.hexdigits)
_PHRASE_ALPHABET = string.ascii_uppercase + string.digits
_NON_HEX_CHARS = "".join(char for char in _PHRASE_ALPHABET if char not in "0123456789ABCDEF")


def _normalize_hex(text: str) -> str | None:
    token = text.strip()
    if not token or any(char not in _HEX_DIGITS for char in token):
        return None
    if len(token) % 2 == 1:
        token += "0"
    return token.upper()


def _make_secret_key(seed: int) -> list[int]:
    rng = random.Random(seed ^ 0xB17A1)
    positions = list(range(_BLOCK_BITS))
    rng.shuffle(positions)
    mapping = [0] * _BLOCK_BITS
    for start in range(0, _BLOCK_BITS, 2):
        left = positions[start]
        right = positions[start + 1]
        mapping[left] = right
        mapping[right] = left
    return [(mapping[index] - index) % _BLOCK_BITS for index in range(_BLOCK_BITS)]


def _make_activation_phrase(seed: int) -> str:
    rng = random.Random(seed ^ 0xAC71_2026)
    chars = [rng.choice(_PHRASE_ALPHABET) for _ in range(5)]
    chars[0] = rng.choice(_NON_HEX_CHARS)
    return "".join(chars)


def _bytes_to_bits(data: bytes) -> list[int]:
    bits: list[int] = []
    for byte in data:
        for offset in range(7, -1, -1):
            bits.append((byte >> offset) & 1)
    return bits


def _bits_to_bytes(bits: list[int]) -> bytes:
    if not bits:
        return b""

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


def _mix_bits(bits: list[int], shifts: list[int]) -> list[int]:
    if not bits:
        return []

    padded = list(bits)
    while len(padded) % _BLOCK_BITS != 0:
        padded.append(0)

    mixed = [0] * len(padded)
    for block_start in range(0, len(padded), _BLOCK_BITS):
        for index in range(_BLOCK_BITS):
            destination = block_start + ((index + shifts[index]) % _BLOCK_BITS)
            mixed[destination] = padded[block_start + index]
    return mixed


def _unmix_bits(bits: list[int], shifts: list[int]) -> list[int]:
    if not bits:
        return []

    padded = list(bits)
    while len(padded) % _BLOCK_BITS != 0:
        padded.append(0)

    unmixed = [0] * len(padded)
    for block_start in range(0, len(padded), _BLOCK_BITS):
        for index in range(_BLOCK_BITS):
            source = block_start + ((index + shifts[index]) % _BLOCK_BITS)
            unmixed[block_start + index] = padded[source]
    return unmixed


def _mix_bytes(data: bytes, shifts: list[int]) -> bytes:
    return _bits_to_bytes(_mix_bits(_bytes_to_bits(data), shifts))


def _unmix_bytes(data: bytes, shifts: list[int]) -> bytes:
    return _bits_to_bytes(_unmix_bits(_bytes_to_bits(data), shifts))


def _ascii_from_mixed_bytes(data: bytes) -> str:
    trimmed = data.rstrip(b"\x00")
    return trimmed.decode("ascii", errors="replace").replace("\ufffd", "?")


def _ascii_to_bytes(text: str) -> bytes:
    return text.encode("ascii", errors="replace")


def _encode_ascii_with_secret(ascii_message: str, seed: int) -> str:
    return _mix_bytes(_ascii_to_bytes(ascii_message), _make_secret_key(seed)).hex().upper()


def encode_transfer_payload(hex_message: str, seed: int) -> tuple[str | None, str]:
    normalized = _normalize_hex(hex_message)
    if normalized is None:
        return None, "Message should be a hex-string."
    mixed = _mix_bytes(bytes.fromhex(normalized), _make_secret_key(seed))
    return _ascii_from_mixed_bytes(mixed), ""


def encode_receive_payload(ascii_message: str, seed: int) -> str:
    return _encode_ascii_with_secret(ascii_message, seed)


def build_transfer_payload(ascii_message: str, seed: int) -> str:
    return _unmix_bytes(_ascii_to_bytes(ascii_message), _make_secret_key(seed)).hex().upper()


class BitMixerTerminal(BaseTerminal):
    """Bit-permutation wrapper terminal with a hidden seed-derived key."""

    def __init__(self, name: str, seed: int, nested=None) -> None:
        super().__init__(name=name, seed=seed, nested=nested)
        self._secret_key = _make_secret_key(seed)
        self._activation_phrase = _make_activation_phrase(seed)
        self._last_response_ascii: str | None = None

    def get_welcome_message(self) -> str:
        return f"[{self._terminal_id}] Bit-mixing terminal is ready!"

    def send(self, payload: str) -> str:
        raw = payload.strip()
        if not raw:
            return self.get_welcome_message()

        if raw == "man":
            return self._man_text()

        if raw == "transfer":
            return self._transfer_help("Wrong usage. Help:")
        if raw.startswith("transfer(") and raw.endswith(")"):
            return self._handle_transfer(raw[9:-1])
        if raw.startswith("transfer"):
            return self._transfer_help("Wrong usage. Help:")

        if raw == "receive":
            return self._handle_receive()
        if raw.startswith("receive"):
            return self._receive_help("Wrong usage. Help:")

        return self._unknown_help()

    def _man_text(self) -> str:
        return (
            "BitMixer manual:\n"
            "  Use `transfer(<hex-string-message>)` to send a message to the nested subsystem.\n"
            "  - `transfer` permutes bits inside each 16-bit blocks with a hidden permutation schema\n"
            "  - encoded traffic is interpreted as ASCII by the nested terminal\n"
            "  - activation requires sending one specific ASCII phrase once via `transfer`\n"
            "  - use `receive` to fetch the encoded response of the previous transfer"
        )

    def _transfer_help(self, prefix: str) -> str:
        return (
            f"{prefix}\n"
            "transfer(hex-string-message) - send a message to the nested subsystem."
        )

    def _receive_help(self, prefix: str) -> str:
        return (
            f"{prefix}\n"
            "receive - receive the encoded response of the last transfer."
        )

    def _unknown_help(self) -> str:
        return (
            "Unknown command. Help:\n"
            "man - explain the basics of the encoding\n"
            "transfer - transfer data to nested system\n"
            "receive - receive the last response"
        )

    def _handle_transfer(self, hex_message: str) -> str:
        normalized = _normalize_hex(hex_message)
        if normalized is None:
            return "Message should be a hex-string."

        mixed_bytes = _mix_bytes(bytes.fromhex(normalized), self._secret_key)
        mixed_hex = mixed_bytes.hex().upper()
        ascii_message = _ascii_from_mixed_bytes(mixed_bytes)
        if not self._online:
            if ascii_message == self._activation_phrase:
                self._online = True
                lines = [f"sent({mixed_hex})", "Activated."]
                if self._nested is not None:
                    lines.append("Nested system is now reachable.")
                    lines.append(self._nested.get_welcome_message())
                return "\n".join(lines)
            return (
                f"Not available. Transfer message '{self._activation_phrase}' to activate nested subsystem. "
                f"You sent: '{ascii_message}' (hex: {mixed_hex})"
            )

        if self._nested is None:
            return "Transfer failed: no nested system connected."

        try:
            self._last_response_ascii = self.dispatch_child(ascii_message)
        except RuntimeError:
            self._last_response_ascii = None
            return "Transfer failed: no nested system connected."
        return f"sent({mixed_hex})"

    def _handle_receive(self) -> str:
        if self._last_response_ascii is None:
            return "Nothing to receive"
        encoded = _encode_ascii_with_secret(self._last_response_ascii, self._seed)
        self._last_response_ascii = None
        return f"received({encoded})"

"""Substitution-cipher wrapper terminal."""

from __future__ import annotations

import random
import string

from server.base_terminal import BaseTerminal

_DIGIT_ALPHABET = "0123456789"
_HEX_DIGITS = set(string.hexdigits)


def _make_formula_coefficients(seed: int) -> tuple[int, int, int]:
    rng = random.Random(seed ^ 0xC1A0_E202)
    while True:
        quad = rng.randrange(1, 256)
        linear = rng.randrange(1, 256)
        offset = rng.randrange(0, 256)
        digit_mapping = build_byte_mapping(10, quad=quad, linear=linear, offset=offset)
        byte_mapping = build_byte_mapping(256, quad=quad, linear=linear, offset=offset)
        digit_fixed = sum(1 for index, value in enumerate(digit_mapping) if index == value)
        byte_fixed = sum(1 for index, value in enumerate(byte_mapping) if index == value)
        if digit_fixed <= 2 and byte_fixed <= 8:
            return quad, linear, offset


def _make_activation_phrase(seed: int) -> str:
    rng = random.Random(seed ^ 0xC17A_2026)
    while True:
        phrase = "".join(rng.choice(_DIGIT_ALPHABET) for _ in range(6))
        if len(set(phrase)) >= 4:
            return phrase


def _score_symbol(code: int, *, bank_size: int, quad: int, linear: int, offset: int) -> int:
    return (quad * code * code + linear * code + offset) % bank_size


def build_byte_mapping(bank_size: int, *, quad: int, linear: int, offset: int) -> list[int]:
    used = [False] * bank_size
    mapping: list[int] = [0] * bank_size
    for source_code in range(bank_size):
        destination = _score_symbol(
            source_code,
            bank_size=bank_size,
            quad=quad,
            linear=linear,
            offset=offset,
        )
        while used[destination]:
            destination = (destination + 1) % bank_size
        used[destination] = True
        mapping[source_code] = destination
    return mapping


def _invert_mapping(mapping: list[int]) -> list[int]:
    inverse = [0] * len(mapping)
    for source_code, destination_code in enumerate(mapping):
        inverse[destination_code] = source_code
    return inverse


def encode_token(plaintext: str, *, quad: int, linear: int, offset: int) -> str:
    mapping = build_byte_mapping(10, quad=quad, linear=linear, offset=offset)
    return "".join(_DIGIT_ALPHABET[mapping[int(char)]] for char in plaintext)


def _decode_token(ciphertext: str, *, quad: int, linear: int, offset: int) -> str | None:
    if not ciphertext or any(char not in _DIGIT_ALPHABET for char in ciphertext):
        return None
    inverse = _invert_mapping(build_byte_mapping(10, quad=quad, linear=linear, offset=offset))
    return "".join(_DIGIT_ALPHABET[inverse[int(char)]] for char in ciphertext)


def _encode_bytes(data: bytes, *, quad: int, linear: int, offset: int) -> bytes:
    mapping = build_byte_mapping(256, quad=quad, linear=linear, offset=offset)
    return bytes(mapping[byte] for byte in data)


def _decode_bytes(data: bytes, *, quad: int, linear: int, offset: int) -> bytes:
    inverse = _invert_mapping(build_byte_mapping(256, quad=quad, linear=linear, offset=offset))
    return bytes(inverse[byte] for byte in data)


def encode_text_for_send(message: str, *, quad: int, linear: int, offset: int) -> str:
    return _encode_bytes(message.encode("latin-1"), quad=quad, linear=linear, offset=offset).hex()


def decode_hex_payload(payload_hex: str, *, quad: int, linear: int, offset: int) -> tuple[str | None, str]:
    normalized = payload_hex.strip()
    if not normalized or any(char not in _HEX_DIGITS for char in normalized):
        return None, "Expected hex bytes, for example `4fa0`."
    if len(normalized) % 2 == 1:
        normalized += "0"
    decoded = _decode_bytes(bytes.fromhex(normalized), quad=quad, linear=linear, offset=offset)
    return decoded.decode("latin-1"), ""


class CipherTerminal(BaseTerminal):
    """Wrapper terminal based on a greedy substitution cipher."""

    def __init__(self, name: str, seed: int, nested=None) -> None:
        super().__init__(name=name, seed=seed, nested=nested)
        self._quad, self._linear, self._offset = _make_formula_coefficients(seed)
        self._activation_phrase = _make_activation_phrase(seed)

    def get_welcome_message(self) -> str:
        return "Cipher terminal is ready. Use HELP for formula hints."

    def send(self, payload: str) -> str:
        raw = payload.strip()
        if not raw:
            return self.get_welcome_message()

        parts = raw.split(None, 1)
        command = parts[0].upper()

        if command == "HELP":
            return self._help_text()
        if command == "STATE":
            return self._render_state()
        if command == "ACTIVATE":
            if len(parts) < 2 or not parts[1].strip():
                return f"[{self._terminal_id}] ACTIVATE requires <digits>."
            return self._handle_activate(parts[1].strip())
        if command == "SEND":
            if len(parts) < 2 or not parts[1].strip():
                return f"[{self._terminal_id}] SEND requires <hex>."
            return self._handle_send(parts[1].strip())

        return f"[{self._terminal_id}] Unknown command {parts[0]!r}. Use HELP."

    def _handle_activate(self, ciphertext: str) -> str:
        decoded = _decode_token(
            ciphertext,
            quad=self._quad,
            linear=self._linear,
            offset=self._offset,
        )
        if decoded is None:
            return self._render_state(status="ACTIVATE failed: expected digits 0-9 only.")
        if decoded != self._activation_phrase:
            return self._render_state(
                status=f"ACTIVATE failed: decoded {decoded!r}; expected activation phrase."
            )

        self._online = True
        child_response = "offline"
        if self._nested is not None:
            child_response = self._nested.get_welcome_message()
        return self._render_state(
            status="UPLINK ONLINE",
            child_hex=encode_text_for_send(
                child_response,
                quad=self._quad,
                linear=self._linear,
                offset=self._offset,
            ),
        )

    def _handle_send(self, payload_hex: str) -> str:
        if not self._online:
            return self._render_state(status="SEND blocked: uplink locked.")

        decoded, error = decode_hex_payload(
            payload_hex,
            quad=self._quad,
            linear=self._linear,
            offset=self._offset,
        )
        if decoded is None:
            return self._render_state(status=f"SEND failed: {error}")

        if self._nested is None:
            response = "offline"
        else:
            try:
                response = self.dispatch_child(decoded)
            except RuntimeError:
                response = "offline"

        return self._render_state(
            status=f"SENT decoded={decoded!r}",
            child_hex=encode_text_for_send(
                response,
                quad=self._quad,
                linear=self._linear,
                offset=self._offset,
            ),
        )

    def _help_text(self) -> str:
        formula = self._formula_text("N")
        return (
            f"[{self._terminal_id}] Commands:\n"
            "  ACTIVATE <digits> - unlock uplink through the digit bank encoding and activation phrase\n"
            "  SEND <hex>        - communicate with uplink through the byte bank encoding\n"
            "  STATE             - print activation phrase, and formula\n"
            "  HELP              - commands and rules\n"
            "Rules:\n"
            f"  Encoding formula: {formula}\n"
            "  Build the substitution table by source character code in ascending order.\n"
            "  If a scored slot is busy, walk forward cyclically until the first free slot.\n"
            "  ACTIVATE uses the digit bank 0..9 (N=10).\n"
            "  SEND uses the full byte bank 0..255 (N=256) and expects hex bytes.\n"
            "  Child responses are returned through the same byte-bank substitution."
        )

    def _formula_text(self, modulus: str | int) -> str:
        return (
            f"h(x) = ({self._quad}*x*x + {self._linear}*x + {self._offset}) mod {modulus}"
        )

    def _render_state(self, *, status: str | None = None, child_hex: str | None = None) -> str:
        lines = [
            f"[{self._terminal_id}] CIPHER",
            f"uplink: {'online' if self._online else 'locked'}",
            f"activation-phrase: {self._activation_phrase}",
        ]
        if status is not None:
            lines.append(f"status: {status}")
        if child_hex is not None:
            lines.append(f"uplink-response: {child_hex}")
        return "\n".join(lines)

"""Polynomial-hash wrapper terminal."""

from __future__ import annotations

import random
import string

from server.base_terminal import BaseTerminal

_MODULUS = 4096
_HEX_DIGITS = set(string.hexdigits.upper())
_PHRASE_ALPHABET = string.ascii_uppercase + string.digits
_EXAMPLE_ALPHABET = string.ascii_uppercase + string.digits
_WRONG_HASH_MESSAGE = "WRONG HASH VALUE. USE RIGHT POLINOMIAL HASH!"
_ACT_ATTEMPT_LIMIT = 128
_ACT_LIMIT_MESSAGE = "ACT LIMIT REACHED. DO NOT BRUTEFORCE THE POLINOMIAL HASH."


def _hash_message(message: str, parameter: int) -> str:
    """Return the seed-specific polynomial hash as three uppercase hex digits."""
    data = message.encode("utf-8")
    total = 0
    factor = 1
    for byte in data:
        total = (total + (byte * factor)) % _MODULUS
        factor = (factor * parameter) % _MODULUS
    return f"{total:03X}"


def _make_polynomial_parameter(seed: int) -> int:
    rng = random.Random(seed ^ 0x1457_1A)
    return rng.randrange(3, 256, 2)


def _make_activation_phrases(seed: int) -> list[str]:
    rng = random.Random(seed ^ 0xA371_CAFE)
    phrases: list[str] = []
    while len(phrases) < 3:
        phrase = "".join(rng.choice(_PHRASE_ALPHABET) for _ in range(5))
        if phrase not in phrases:
            phrases.append(phrase)
    return phrases


def _make_hex_examples(seed: int) -> list[str]:
    rng = random.Random(seed ^ 0xBADC_0DE)
    examples: list[str] = []
    while len(examples) < 16:
        length = rng.randint(1, 10)
        message = "".join(rng.choice(_EXAMPLE_ALPHABET) for _ in range(length))
        if message in {"A", "BA", "AAA"}:
            continue
        if message not in examples:
            examples.append(message)
    return examples


class HashTerminal(BaseTerminal):
    """Three-step polynomial-hash wrapper terminal."""

    def __init__(self, name: str, seed: int, nested=None) -> None:
        super().__init__(name=name, seed=seed, nested=nested)
        self._parameter = _make_polynomial_parameter(seed)
        self._activation_phrases = _make_activation_phrases(seed)
        self._activation_step = 0
        self._act_attempts = 0
        self._hex_examples = _make_hex_examples(seed)
        self._hex_index = 0

    def get_welcome_message(self) -> str:
        return (
            "HASH-TERMINAL\n"
            "CMDS: ACT, HEX, HLP, SND\n"
            "USE ACT TO ACTIVATE TERMINAL\n"
            "USE HEX TO GET HASH EXAMPLES\n"
            "USE HLP FOR HELP\n"
            "USE SND TO COMMUNICATE WITH NESTED TERMINAL AFTER ACTIVATION"
        )

    def send(self, payload: str) -> str:
        raw_payload = payload.strip()
        if not raw_payload:
            return self.get_welcome_message()

        parts = raw_payload.split(None, 1)
        command = parts[0]

        if command == "HLP":
            return self._help_text()
        if command == "HEX":
            return self._handle_hex()
        if command == "ACT":
            return self._handle_act(parts[1] if len(parts) > 1 else "")
        if command == "SND":
            return self._handle_snd(parts[1] if len(parts) > 1 else "")
        return "UNKNOWN COMMAND. USE HLP."

    def _handle_act(self, argument: str) -> str:
        if self._online:
            return "HASH-TERMINAL IS ALREADY ONLINE."
        if self._act_attempts >= _ACT_ATTEMPT_LIMIT:
            return _ACT_LIMIT_MESSAGE
        self._act_attempts += 1
        candidate, ok = self._parse_hash_argument(argument)
        if not ok:
            return "ACT REQUIRES EXACTLY ONE 3-DIGIT UPPERCASE HEX HASH."
        expected = _hash_message(self._current_phrase(), self._parameter)
        if candidate != expected:
            self._activation_step = 0
            return _WRONG_HASH_MESSAGE

        self._activation_step += 1
        if self._activation_step < 3:
            return (
                f"OK {self._activation_step} of 3. "
                f"NEXT ACTIVATION PHRASE: {self._current_phrase()}"
            )

        self._online = True
        if self._nested is None:
            return "OK 3 of 3. ACTIVATED"
        return f"OK 3 of 3. ACTIVATED\n{self._nested.get_welcome_message()}"

    def _handle_hex(self) -> str:
        message = self._hex_examples[self._hex_index % len(self._hex_examples)]
        self._hex_index += 1
        return (
            f"HASH IS POLINOMIAL.\nEXAMPLE: [{message}] -> "
            f"{_hash_message(message, self._parameter)}"
        )

    def _handle_snd(self, argument: str) -> str:
        if not self._online:
            return "SND IS INACTIVE. USE ACT TO ACTIVATE TERMINAL FIRST."
        if self._nested is None:
            return "SND FAILED: NO NESTED TERMINAL CONNECTED."

        parts = argument.split(None, 1)
        if len(parts) != 2:
            return "SND REQUIRES: SND hhh msg"
        candidate, ok = self._parse_hash_argument(parts[0])
        if not ok:
            return "SND REQUIRES hhh AS 3 UPPERCASE HEX DIGITS."
        message = parts[1]
        if candidate != _hash_message(message, self._parameter):
            return _WRONG_HASH_MESSAGE
        return f"RESPONSE: {self.dispatch_child(message)}"

    def _parse_hash_argument(self, text: str) -> tuple[str, bool]:
        token = text.strip()
        return token, len(token) == 3 and all(ch in _HEX_DIGITS for ch in token)

    def _current_phrase(self) -> str:
        return self._activation_phrases[min(self._activation_step, len(self._activation_phrases) - 1)]

    def _help_text(self) -> str:
        send_line = "SND hhh msg" if self._online else "SND hhh msg (INACTIVE)"
        state = "ONLINE" if self._online else "OFFLINE"
        return (
            f"HASH-TERMINAL IS {state}\n\n"
            "SYNTAX:\n"
            "ACT hhh\n"
            "HEX\n"
            "HLP\n"
            f"{send_line}\n\n"
            "hhh - 3 DIGITS msg HASH.\n\n"
            "HASH EXAMPLES:\n"
            f"A -> {_hash_message('A', self._parameter)}\n"
            f"BA -> {_hash_message('BA', self._parameter)}\n"
            f"AAA -> {_hash_message('AAA', self._parameter)}\n\n"
            "USE HEX FOR MORE HASH EXAMPLES.\n\n"
            f"ACT HAS A LIMIT OF {_ACT_ATTEMPT_LIMIT} CALLS. DO NOT BRUTEFORCE.\n\n"
            f"ACTIVATION PHRASE: {self._current_phrase()}"
        )

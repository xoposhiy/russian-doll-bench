from server.base_terminal import BaseTerminal
from server.terminals.bitmixer import (
    BitMixerTerminal,
    build_transfer_payload,
    encode_receive_payload,
    encode_transfer_payload,
)
from server.terminals.bitmixer.bitmixer_terminal import _mix_bytes
from server.terminals.main import MainTerminal


SEED = 7


class EchoTerminal(BaseTerminal):
    def __init__(self, name: str, seed: int, nested=None) -> None:
        super().__init__(name=name, seed=seed, nested=None)
        self._online = True
        self._last_payload = ""

    def get_welcome_message(self) -> str:
        return f"[{self._terminal_id}] Echo ready."

    def send(self, payload: str) -> str:
        self._last_payload = payload
        return f"ECHO:{payload}"


def make_main() -> MainTerminal:
    return MainTerminal("INNER", seed=0)


def make_echo() -> EchoTerminal:
    return EchoTerminal("ECHO", seed=0)


def make_terminal(seed: int = SEED, nested=None) -> BitMixerTerminal:
    return BitMixerTerminal("BIT", seed=seed, nested=nested)


def _transfer_result_hex(payload_hex: str, seed: int) -> str:
    normalized = payload_hex if len(payload_hex) % 2 == 0 else payload_hex + "0"
    terminal = make_terminal(seed=seed)
    return _mix_bytes(bytes.fromhex(normalized), terminal._secret_key).hex().upper()  # noqa: SLF001


def test_welcome_is_short():
    assert make_terminal().send("") == "[BIT] Bit-mixing terminal is ready!"


def test_man_explains_basics():
    response = make_terminal().send("man")
    assert "transfer(<hex-string-message>)" in response
    assert "16-bit blocks" in response
    assert "ASCII" in response
    assert "activation requires" in response


def test_transfer_wrong_usage_prints_help():
    response = make_terminal().send("transfer")
    assert response.startswith("Wrong usage. Help:")
    assert "transfer(hex-string-message)" in response


def test_unknown_command_prints_short_help():
    response = make_terminal().send("?")
    assert response.startswith("Unknown command. Help:")
    assert "man - explain the basics of the encoding" in response


def test_transfer_rejects_non_hex_payload():
    assert make_terminal().send("transfer(NOPE)") == "Message should be a hex-string."


def test_offline_transfer_returns_sent_and_activation_hint():
    terminal = make_terminal(seed=SEED)
    response = terminal.send("transfer(00)")
    assert response.startswith("Not available. Transfer message '")
    assert "activate nested subsystem" in response
    assert "You sent: '" in response
    assert " (hex: " in response


def test_activation_phrase_contains_non_hex_character():
    phrase = make_terminal(seed=SEED)._activation_phrase  # noqa: SLF001
    assert any(char not in "0123456789ABCDEF" for char in phrase)


def test_correct_activation_transfer_activates_and_shows_nested_welcome():
    terminal = make_terminal(seed=SEED, nested=make_main())
    payload = build_transfer_payload(terminal._activation_phrase, seed=SEED)  # noqa: SLF001
    response = terminal.send(f"transfer({payload})")
    assert f"sent({_transfer_result_hex(payload, seed=SEED)})" in response
    assert "Activated." in response
    assert "Nested system is now reachable." in response
    assert "Final system terminal" in response
    assert terminal.is_online is True


def test_online_transfer_forwards_to_child():
    nested = make_echo()
    terminal = make_terminal(seed=SEED, nested=nested)
    activation_payload = build_transfer_payload(terminal._activation_phrase, seed=SEED)  # noqa: SLF001
    terminal.send(f"transfer({activation_payload})")
    payload_hex = build_transfer_payload("PING", seed=SEED)
    sent_ascii, error = encode_transfer_payload(payload_hex, seed=SEED)
    assert error == ""
    assert sent_ascii == "PING"
    response = terminal.send(f"transfer({payload_hex})")
    assert response == f"sent({_transfer_result_hex(payload_hex, seed=SEED)})"
    assert nested._last_payload == "PING"  # noqa: SLF001


def test_online_transfer_without_child_reports_recoverable_error():
    terminal = make_terminal(seed=SEED, nested=None)
    activation_payload = build_transfer_payload(terminal._activation_phrase, seed=SEED)  # noqa: SLF001
    terminal.send(f"transfer({activation_payload})")
    response = terminal.send(f"transfer({build_transfer_payload('PING', seed=SEED)})")
    assert response == "Transfer failed: no nested system connected."


def test_receive_wrong_usage_prints_help():
    response = make_terminal().send("receive 12")
    assert response.startswith("Wrong usage. Help:")
    assert "receive - receive the encoded response" in response


def test_receive_returns_encoded_buffer_once():
    nested = make_echo()
    terminal = make_terminal(seed=SEED, nested=nested)
    activation_payload = build_transfer_payload(terminal._activation_phrase, seed=SEED)  # noqa: SLF001
    terminal.send(f"transfer({activation_payload})")
    transfer_hex = build_transfer_payload("HELP", seed=SEED)
    terminal.send(f"transfer({transfer_hex})")
    received = terminal.send("receive")
    expected_hex = encode_receive_payload("ECHO:HELP", seed=SEED)
    assert received == f"received({expected_hex})"
    assert terminal.send("receive") == "Nothing to receive"

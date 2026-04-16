from server.base_terminal import BaseTerminal
from server.terminals.cipher import (
    CipherTerminal,
    build_byte_mapping,
    decode_hex_payload,
    encode_text_for_send,
    encode_token,
)
from server.terminals.main import MainTerminal


SEED = 17


class EchoTerminal(BaseTerminal):
    def __init__(self, name: str, seed: int, nested=None) -> None:
        super().__init__(name=name, seed=seed, nested=None)
        self.last_payload = ""

    def get_welcome_message(self) -> str:
        return f"[{self._terminal_id}] Echo ready."

    def send(self, payload: str) -> str:
        self.last_payload = payload
        return f"ECHO:{payload}"


def make_main() -> MainTerminal:
    return MainTerminal("INNER", seed=0)


def make_echo() -> EchoTerminal:
    return EchoTerminal("ECHO", seed=0)


def make_terminal(seed: int = SEED, nested=None) -> CipherTerminal:
    return CipherTerminal("CIPHER", seed=seed, nested=nested)


def test_mapping_is_a_permutation_for_both_banks():
    terminal = make_terminal()
    digit_mapping = build_byte_mapping(
        10,
        quad=terminal._quad,  # noqa: SLF001
        linear=terminal._linear,  # noqa: SLF001
        offset=terminal._offset,  # noqa: SLF001
    )
    byte_mapping = build_byte_mapping(
        256,
        quad=terminal._quad,  # noqa: SLF001
        linear=terminal._linear,  # noqa: SLF001
        offset=terminal._offset,  # noqa: SLF001
    )
    assert sorted(digit_mapping) == list(range(10))
    assert sorted(byte_mapping) == list(range(256))


def test_welcome_is_short():
    assert make_terminal().send("") == "Cipher terminal is ready. Use HELP for formula hints."


def test_help_mentions_formula_and_collision_rule():
    response = make_terminal().send("HELP")
    assert "Encoding formula:" in response
    assert "first free slot" in response
    assert "ACTIVATE uses the digit bank 0..9 (N=10)." in response
    assert "SEND uses the full byte bank 0..255 (N=256)" in response


def test_state_shows_phrase():
    response = make_terminal().send("STATE")
    assert "[CIPHER] CIPHER" in response
    assert "uplink: locked" in response
    assert "activation-phrase:" in response
    assert "status:" not in response


def test_activate_requires_digits_only():
    response = make_terminal().send("ACTIVATE 12af")
    assert "expected digits 0-9 only" in response


def test_wrong_activation_keeps_terminal_locked():
    terminal = make_terminal()
    response = terminal.send("ACTIVATE 000000")
    assert "ACTIVATE failed:" in response
    assert terminal.is_online is False


def test_correct_activation_returns_encoded_child_welcome():
    terminal = make_terminal(nested=make_main())
    payload = encode_token(
        terminal._activation_phrase,  # noqa: SLF001
        quad=terminal._quad,  # noqa: SLF001
        linear=terminal._linear,  # noqa: SLF001
        offset=terminal._offset,  # noqa: SLF001
    )
    response = terminal.send(f"ACTIVATE {payload}")
    assert "status: UPLINK ONLINE" in response
    assert "uplink-response:" in response
    encoded = response.split("uplink-response: ", 1)[1]
    decoded, error = decode_hex_payload(
        encoded,
        quad=terminal._quad,  # noqa: SLF001
        linear=terminal._linear,  # noqa: SLF001
        offset=terminal._offset,  # noqa: SLF001
    )
    assert error == ""
    assert decoded == make_main().get_welcome_message()


def test_send_is_blocked_while_locked():
    response = make_terminal().send("SEND 00")
    assert "SEND blocked: uplink locked." in response


def test_send_decodes_payload_and_forwards_to_child():
    nested = make_echo()
    terminal = make_terminal(nested=nested)
    activation_payload = encode_token(
        terminal._activation_phrase,  # noqa: SLF001
        quad=terminal._quad,  # noqa: SLF001
        linear=terminal._linear,  # noqa: SLF001
        offset=terminal._offset,  # noqa: SLF001
    )
    terminal.send(f"ACTIVATE {activation_payload}")
    payload = encode_text_for_send(
        "PING",
        quad=terminal._quad,  # noqa: SLF001
        linear=terminal._linear,  # noqa: SLF001
        offset=terminal._offset,  # noqa: SLF001
    )
    response = terminal.send(f"SEND {payload}")
    assert "status: SENT decoded='PING'" in response
    assert nested.last_payload == "PING"
    encoded = response.split("uplink-response: ", 1)[1]
    decoded, error = decode_hex_payload(
        encoded,
        quad=terminal._quad,  # noqa: SLF001
        linear=terminal._linear,  # noqa: SLF001
        offset=terminal._offset,  # noqa: SLF001
    )
    assert error == ""
    assert decoded == "ECHO:PING"


def test_send_rejects_non_hex_payload():
    terminal = make_terminal()
    activation_payload = encode_token(
        terminal._activation_phrase,  # noqa: SLF001
        quad=terminal._quad,  # noqa: SLF001
        linear=terminal._linear,  # noqa: SLF001
        offset=terminal._offset,  # noqa: SLF001
    )
    terminal.send(f"ACTIVATE {activation_payload}")
    response = terminal.send("SEND xyz")
    assert "Expected hex bytes" in response

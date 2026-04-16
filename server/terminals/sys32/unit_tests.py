"""Unit tests for Sys32Terminal."""

from server.terminals.main import MainTerminal
from server.terminals.sys32 import (
    ALPHABET,
    Sys32Terminal,
    _bd32_decode,
    _bd32_encode,
)


SEED = 42


def make_terminal(seed: int = SEED, nested=None) -> Sys32Terminal:
    return Sys32Terminal("SYS32", seed=seed, nested=nested)


def make_nested() -> MainTerminal:
    return MainTerminal("INNER", seed=0)


class TestCodec:
    def test_alphabet_length(self):
        assert len(ALPHABET) == 32

    def test_alphabet_no_confusable_chars(self):
        for bad in "0OI1":
            assert bad not in ALPHABET

    def test_terminal_alphabet_is_seed_derived_permutation(self):
        terminal = make_terminal()
        assert sorted(terminal._alphabet) == sorted(ALPHABET)

    def test_same_seed_same_alphabet(self):
        assert make_terminal(seed=7)._alphabet == make_terminal(seed=7)._alphabet

    def test_different_seeds_different_alphabet(self):
        assert make_terminal(seed=1)._alphabet != make_terminal(seed=2)._alphabet

    def test_roundtrip_ascii(self):
        for text in ("HELP", "ACTIVATE TERMINAL", "hello world", "ABC123"):
            assert _bd32_decode(_bd32_encode(text)) == (text, "")

    def test_roundtrip_empty(self):
        assert _bd32_decode(_bd32_encode("")) == ("", "")

    def test_roundtrip_single_char(self):
        for char in "ABCXYZ 0":
            assert _bd32_decode(_bd32_encode(char)) == (char, "")

    def test_decode_invalid_char_returns_error(self):
        decoded, err = _bd32_decode("!!!invalid!!!")
        assert decoded is None
        assert err != ""

    def test_decode_confusable_char_rejected(self):
        for bad in ("0BC", "OBC", "IBC", "1BC"):
            decoded, _ = _bd32_decode(bad)
            assert decoded is None

    def test_decode_case_insensitive(self):
        encoded = _bd32_encode("HELLO")
        decoded, _ = _bd32_decode(encoded.lower())
        assert decoded == "HELLO"

    def test_delta_encoding_changes_representation(self):
        assert _bd32_encode("AA") != _bd32_encode("AB")

    def test_delta_wraps_mod_256(self):
        text = chr(200) + chr(50)
        assert _bd32_decode(_bd32_encode(text)) == (text, "")


class TestWelcomeAndHelp:
    def test_empty_payload_returns_welcome(self):
        assert "SYS32" in make_terminal().send("")

    def test_welcome_is_brief(self):
        terminal = make_terminal()
        assert terminal.send("") == "[SYS32] Ready to talk!\n"

    def test_settings_contains_raw_token(self):
        terminal = make_terminal()
        assert terminal._token in terminal.send("SETTINGS")

    def test_settings_contains_alphabet(self):
        terminal = make_terminal()
        assert terminal._alphabet in terminal.send("SETTINGS")

    def test_help_invites_decode_experiment(self):
        assert "DECODE" in make_terminal().send("HELP")

    def test_help_shows_all_commands(self):
        response = make_terminal().send("HELP")
        for cmd in ("AUTHENTICATE", "SEND", "DECODE", "SETTINGS", "HELP"):
            assert cmd in response

    def test_settings_show_alphabet(self):
        terminal = make_terminal()
        assert terminal._alphabet in terminal.send("SETTINGS")

    def test_help_case_insensitive(self):
        assert "AUTHENTICATE" in make_terminal().send("help")


class TestAuthenticate:
    def test_correct_token_activates(self):
        terminal = make_terminal(nested=make_nested())
        response = terminal.send(f"AUTHENTICATE {terminal._encode(terminal._token)}")
        assert terminal.is_online
        assert "ONLINE" in response

    def test_wrong_token_does_not_activate(self):
        terminal = make_terminal()
        terminal.send(f"AUTHENTICATE {terminal._encode('wrong-token')}")
        assert not terminal.is_online

    def test_wrong_token_reports_mismatch(self):
        terminal = make_terminal()
        response = terminal.send(f"AUTHENTICATE {terminal._encode('wrong-token')}")
        assert "mismatch" in response.lower() or "failed" in response.lower()

    def test_missing_argument_returns_error(self):
        response = make_terminal().send("AUTHENTICATE")
        assert "argument" in response.lower() or "AUTHENTICATE" in response

    def test_invalid_encoding_returns_error(self):
        response = make_terminal().send("AUTHENTICATE 0INVALID0")
        assert "failed" in response.lower() or "invalid" in response.lower()

    def test_activation_shows_nested_welcome(self):
        terminal = make_terminal(nested=make_nested())
        response = terminal.send(f"AUTHENTICATE {terminal._encode(terminal._token)}")
        encoded_part = response.split("Nested system welcome message (encoded):", 1)[1].strip()
        decoded, err = terminal._decode(encoded_part)
        assert err == ""
        assert "INNER" in decoded

    def test_is_online_initially_false(self):
        assert not make_terminal().is_online


class TestDecode:
    def test_decode_valid_string(self):
        terminal = make_terminal()
        response = terminal.send(f"DECODE {terminal._encode('HELLO')}")
        assert "HELLO" in response

    def test_decode_shows_terminal_id(self):
        terminal = make_terminal()
        assert "SYS32" in terminal.send(f"DECODE {terminal._encode('X')}")

    def test_decode_invalid_returns_error(self):
        response = make_terminal().send("DECODE 0BAD0")
        assert "failed" in response.lower() or "invalid" in response.lower()

    def test_decode_missing_arg_returns_error(self):
        response = make_terminal().send("DECODE")
        assert "argument" in response.lower() or "DECODE" in response

    def test_decode_does_not_activate(self):
        terminal = make_terminal()
        terminal.send(f"DECODE {terminal._encode(terminal._token)}")
        assert not terminal.is_online


class TestSend:
    def _activate(self, terminal: Sys32Terminal) -> None:
        terminal.send(f"AUTHENTICATE {terminal._encode(terminal._token)}")
        assert terminal.is_online

    def test_send_blocked_when_offline(self):
        terminal = make_terminal()
        response = terminal.send(f"SEND {terminal._encode('hello')}")
        assert "Authenticate" in response or "not available" in response.lower()

    def test_send_without_arg_fails(self):
        terminal = make_terminal(nested=make_nested())
        self._activate(terminal)
        response = terminal.send("SEND")
        assert "argument" in response.lower() or "SEND" in response

    def test_send_invalid_encoding_fails(self):
        terminal = make_terminal(nested=make_nested())
        self._activate(terminal)
        response = terminal.send("SEND 0BADINPUT0")
        assert "failed" in response.lower() or "invalid" in response.lower()

    def test_send_forwards_decoded_to_nested(self):
        nested = make_nested()
        terminal = make_terminal(nested=nested)
        self._activate(terminal)
        terminal.send(f"SEND {terminal._encode('ACTIVATE TERMINAL')}")
        assert nested.is_online

    def test_send_response_is_bd32_encoded(self):
        terminal = make_terminal(nested=make_nested())
        self._activate(terminal)
        response = terminal.send(f"SEND {terminal._encode('HELP')}")
        assert "encoded-response:" in response

    def test_send_response_decodable(self):
        terminal = make_terminal(nested=make_nested())
        self._activate(terminal)
        response = terminal.send(f"SEND {terminal._encode('HELP')}")
        encoded_part = response.split("encoded-response:", 1)[1].strip()
        decoded, err = terminal._decode(encoded_part)
        assert err == ""
        assert decoded

    def test_send_without_nested_fails_gracefully(self):
        terminal = make_terminal(nested=None)
        self._activate(terminal)
        response = terminal.send(f"SEND {terminal._encode('hello')}")
        assert "no nested" in response.lower() or "not connected" in response.lower()


class TestReproducibility:
    def test_same_seed_same_token(self):
        assert make_terminal(seed=7)._token == make_terminal(seed=7)._token

    def test_different_seeds_different_tokens(self):
        assert make_terminal(seed=1)._token != make_terminal(seed=2)._token

    def test_unknown_command_includes_terminal_id(self):
        assert "SYS32" in make_terminal().send("BADCMD")

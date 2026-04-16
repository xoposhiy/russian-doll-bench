"""Unit tests for HashTerminal."""

from server.base_terminal import BaseTerminal
from server.terminals.hash import HashTerminal, _hash_message
from server.terminals.hash.hash_terminal import _ACT_ATTEMPT_LIMIT, _ACT_LIMIT_MESSAGE
from server.terminals.main import MainTerminal


SEED = 42


class EchoTerminal(BaseTerminal):
    def __init__(self, name: str, seed: int, nested=None) -> None:
        super().__init__(name=name, seed=seed, nested=None)

    def get_welcome_message(self) -> str:
        return "[ECHO] READY"

    def send(self, payload: str) -> str:
        self._online = True
        return payload


def make_terminal(seed: int = SEED, nested=None) -> HashTerminal:
    return HashTerminal("HASH", seed=seed, nested=nested)


def make_main() -> MainTerminal:
    return MainTerminal("INNER", seed=0)


def make_echo() -> EchoTerminal:
    return EchoTerminal("ECHO", seed=0)


class TestHelpers:
    def test_hash_message_formats_three_hex_digits(self):
        assert _hash_message("A", 3) == "041"

    def test_hash_message_uses_utf8_bytes(self):
        value = _hash_message("A!", 5)
        assert value == f"{(65 + 33 * 5) % 4096:03X}"

    def test_hash_message_handles_unicode(self):
        assert _hash_message("A€", 7) == _hash_message("A€", 7)


class TestWelcomeAndHelp:
    def test_empty_payload_returns_compact_welcome(self):
        response = make_terminal().send("")
        assert response.startswith("HASH-TERMINAL")
        assert "CMDS: ACT, HEX, HLP, SND" in response

    def test_help_shows_offline_state_and_snd_inactive(self):
        response = make_terminal().send("HLP")
        assert "HASH-TERMINAL IS OFFLINE" in response
        assert "SND hhh msg (INACTIVE)" in response
        assert f"ACT HAS A LIMIT OF {_ACT_ATTEMPT_LIMIT} CALLS. DO NOT BRUTEFORCE." in response

    def test_help_shows_seed_specific_hash_examples(self):
        terminal = make_terminal()
        response = terminal.send("HLP")
        assert f"A -> {_hash_message('A', terminal._parameter)}" in response  # noqa: SLF001
        assert f"BA -> {_hash_message('BA', terminal._parameter)}" in response  # noqa: SLF001
        assert f"AAA -> {_hash_message('AAA', terminal._parameter)}" in response  # noqa: SLF001

    def test_hex_returns_progressing_deterministic_examples(self):
        a = make_terminal(seed=7)
        b = make_terminal(seed=7)
        assert a.send("HEX") == b.send("HEX")
        assert a.send("HEX") == b.send("HEX")
        assert a.send("HEX") != a.send("HEX")


class TestActivation:
    def test_correct_three_step_sequence_activates_terminal(self):
        terminal = make_terminal(nested=make_main())

        first = terminal.send(f"ACT {_hash_message(terminal._activation_phrases[0], terminal._parameter)}")  # noqa: SLF001
        assert first == f"OK 1 of 3. NEXT ACTIVATION PHRASE: {terminal._activation_phrases[1]}"  # noqa: SLF001

        second = terminal.send(f"ACT {_hash_message(terminal._activation_phrases[1], terminal._parameter)}")  # noqa: SLF001
        assert second == f"OK 2 of 3. NEXT ACTIVATION PHRASE: {terminal._activation_phrases[2]}"  # noqa: SLF001

        third = terminal.send(f"ACT {_hash_message(terminal._activation_phrases[2], terminal._parameter)}")  # noqa: SLF001
        assert terminal.is_online is True
        assert third.startswith("OK 3 of 3. ACTIVATED")
        assert "[INNER] Final system terminal." in third

    def test_wrong_hash_resets_progress(self):
        terminal = make_terminal()
        terminal.send(f"ACT {_hash_message(terminal._activation_phrases[0], terminal._parameter)}")  # noqa: SLF001
        response = terminal.send("ACT 000")
        assert response == "WRONG HASH VALUE. USE RIGHT POLINOMIAL HASH!"
        assert terminal._activation_step == 0  # noqa: SLF001
        assert "ACTIVATION PHRASE: " + terminal._activation_phrases[0] in terminal.send("HLP")  # noqa: SLF001

    def test_invalid_act_argument_reports_expected_shape(self):
        response = make_terminal().send("ACT hello")
        assert response == "ACT REQUIRES EXACTLY ONE 3-DIGIT UPPERCASE HEX HASH."

    def test_help_switches_to_online_after_activation(self):
        terminal = make_terminal()
        for phrase in terminal._activation_phrases:  # noqa: SLF001
            terminal.send(f"ACT {_hash_message(phrase, terminal._parameter)}")  # noqa: SLF001
        response = terminal.send("HLP")
        assert "HASH-TERMINAL IS ONLINE" in response
        assert "(INACTIVE)" not in response

    def test_act_limit_blocks_further_attempts(self):
        terminal = make_terminal()
        for _ in range(_ACT_ATTEMPT_LIMIT):
            terminal.send("ACT 000")
        assert terminal.send("ACT 000") == _ACT_LIMIT_MESSAGE
        assert terminal._activation_step == 0  # noqa: SLF001

    def test_invalid_act_arguments_also_consume_attempt_budget(self):
        terminal = make_terminal()
        for _ in range(_ACT_ATTEMPT_LIMIT):
            terminal.send("ACT nope")
        assert terminal.send("ACT 000") == _ACT_LIMIT_MESSAGE


class TestSend:
    def _activate(self, terminal: HashTerminal) -> None:
        for phrase in terminal._activation_phrases:  # noqa: SLF001
            terminal.send(f"ACT {_hash_message(phrase, terminal._parameter)}")  # noqa: SLF001
        assert terminal.is_online

    def test_send_blocked_before_activation(self):
        response = make_terminal().send("SND 000 HELLO")
        assert response == "SND IS INACTIVE. USE ACT TO ACTIVATE TERMINAL FIRST."

    def test_send_requires_hash_and_message(self):
        terminal = make_terminal(nested=make_echo())
        self._activate(terminal)
        assert terminal.send("SND") == "SND REQUIRES: SND hhh msg"

    def test_send_wrong_hash_uses_exact_error(self):
        terminal = make_terminal(nested=make_echo())
        self._activate(terminal)
        assert terminal.send("SND 000 HELLO") == "WRONG HASH VALUE. USE RIGHT POLINOMIAL HASH!"

    def test_send_forwards_raw_message_to_child(self):
        terminal = make_terminal(nested=make_echo())
        self._activate(terminal)
        message = "HELLO WORLD"
        response = terminal.send(f"SND {_hash_message(message, terminal._parameter)} {message}")  # noqa: SLF001
        assert response == "RESPONSE: HELLO WORLD"

    def test_send_can_activate_nested_main_terminal(self):
        nested = make_main()
        terminal = make_terminal(nested=nested)
        self._activate(terminal)
        message = "ACTIVATE TERMINAL"
        response = terminal.send(f"SND {_hash_message(message, terminal._parameter)} {message}")  # noqa: SLF001
        assert "Task complete" in response
        assert nested.is_online is True

    def test_send_without_nested_reports_missing_child(self):
        terminal = make_terminal()
        self._activate(terminal)
        assert terminal.send("SND ABC TEST") == "SND FAILED: NO NESTED TERMINAL CONNECTED."


class TestDeterminism:
    def test_same_seed_same_parameter(self):
        assert make_terminal(seed=9)._parameter == make_terminal(seed=9)._parameter  # noqa: SLF001

    def test_same_seed_same_activation_phrases(self):
        assert make_terminal(seed=5)._activation_phrases == make_terminal(seed=5)._activation_phrases  # noqa: SLF001

    def test_different_seeds_change_terminal_instance(self):
        a = make_terminal(seed=1)
        b = make_terminal(seed=2)
        assert (a._parameter, a._activation_phrases, a._hex_examples) != (  # noqa: SLF001
            b._parameter,  # noqa: SLF001
            b._activation_phrases,  # noqa: SLF001
            b._hex_examples,  # noqa: SLF001
        )

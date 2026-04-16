from pytest import raises

from server.terminal_spec import TerminalBySpecBuilder
from server.terminals import (
    BitMixerTerminal,
    DummyTerminal,
    HashTerminal,
    MainTerminal,
    MazeTerminal,
    Sys32Terminal,
)
from server.terminals.sys32.sys32_terminal import _make_token

BUILDER = TerminalBySpecBuilder()


class TestParseTerminalSpec:
    def test_main_normalizes_to_main(self):
        assert BUILDER.normalize_terminal_spec(" main ") == "main"

    def test_plain_chain_round_trips(self):
        assert BUILDER.normalize_terminal_spec("sys32-maze-sys32") == "sys32-maze-sys32"

    def test_alternative_layers_round_trip(self):
        assert BUILDER.normalize_terminal_spec(" sys32 | maze - hash | dummy ") == "sys32|maze-hash|dummy"

    def test_segment_parameters_round_trip(self):
        assert (
                BUILDER.normalize_terminal_spec("sys32(42)-maze(seed=12121)-sys32(seed=52)")
                == "sys32(42)-maze(seed=12121)-sys32(seed=52)"
        )

    def test_alternative_layer_parameters_round_trip(self):
        assert (
                BUILDER.normalize_terminal_spec("sys32(42) | maze(seed=12121)")
                == "sys32(42)|maze(seed=12121)"
        )

    def test_main_is_rejected_inside_chain(self):
        with raises(ValueError, match="main"):
            BUILDER.parse_terminal_spec("sys32-main")

    def test_main_is_rejected_inside_alternative_layer(self):
        with raises(ValueError, match="main"):
            BUILDER.parse_terminal_spec("main|sys32")

    def test_unknown_terminal_type_is_rejected(self):
        with raises(ValueError, match="Unknown terminal type"):
            BUILDER.parse_terminal_spec("unknown")


class TestBuildTerminalChain:
    def test_main_builds_single_terminal(self):
        outer = BUILDER.build("main", default_seed=42)

        terminals = outer.all_terminals()
        assert len(terminals) == 1
        assert isinstance(outer, MainTerminal)
        assert outer.terminal_id == "SYS1"

    def test_chain_builds_outermost_first(self):
        outer = BUILDER.build("sys32-maze", default_seed=10)

        terminals = outer.all_terminals()
        assert [type(t) for t in terminals] == [Sys32Terminal, MazeTerminal, MainTerminal]
        assert [t.terminal_id for t in terminals] == ["SYS1", "SYS2", "SYS3"]

    def test_hash_chain_builds_hash_terminal(self):
        outer = BUILDER.build("hash", default_seed=10)

        terminals = outer.all_terminals()
        assert [type(t) for t in terminals] == [HashTerminal, MainTerminal]
        assert [t.terminal_id for t in terminals] == ["SYS1", "SYS2"]

    def test_dummy_chain_builds_dummy_terminal(self):
        outer = BUILDER.build("dummy", default_seed=10)

        terminals = outer.all_terminals()
        assert [type(t) for t in terminals] == [DummyTerminal, MainTerminal]
        assert [t.terminal_id for t in terminals] == ["SYS1", "SYS2"]

    def test_bitmixer_chain_builds_bitmixer_terminal(self):
        outer = BUILDER.build("bitmixer", default_seed=10)

        terminals = outer.all_terminals()
        assert [type(t) for t in terminals] == [BitMixerTerminal, MainTerminal]
        assert [t.terminal_id for t in terminals] == ["SYS1", "SYS2"]

    def test_seeded_alternative_build_is_deterministic(self):
        outer = BUILDER.build("sys32|maze", default_seed=0)

        terminals = outer.all_terminals()
        assert [type(t) for t in terminals] == [MazeTerminal, MainTerminal]
        assert [t.terminal_id for t in terminals] == ["SYS1", "SYS2"]

    def test_seeded_alternative_uses_selected_terminal_arguments(self):
        outer = BUILDER.build("sys32(99)|sys32(100)", default_seed=0)

        assert isinstance(outer, Sys32Terminal)
        assert outer._token == _make_token(100)  # noqa: SLF001

    def test_seeded_alternatives_are_chosen_per_layer(self):
        outer = BUILDER.build("sys32|maze-hash|dummy", default_seed=10)

        terminals = outer.all_terminals()
        assert [type(t) for t in terminals] == [MazeTerminal, HashTerminal, MainTerminal]
        assert [t.terminal_id for t in terminals] == ["SYS1", "SYS2", "SYS3"]

    def test_positional_seed_overrides_default(self):
        outer = BUILDER.build("sys32(99)-maze", default_seed=10)

        assert isinstance(outer, Sys32Terminal)
        assert outer._token == _make_token(99)  # noqa: SLF001

"""
Small language for explicit terminal-chain definitions.

Examples:
  main
  sys32
  sys32-maze-sys32
  sys32(42)-maze(12121)-sys32(52)
  hash(seed=7)

The leaf terminal is always MainTerminal and is implicit unless the whole spec
is exactly "main".
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Mapping
import random

from server.base_terminal import BaseTerminal
from server.terminals import (
    BitMixerTerminal,
    CipherTerminal,
    DummyTerminal,
    HashTerminal,
    MainTerminal,
    MazeTerminal,
    Sys32Terminal,
)

DEFAULT_TERMINAL_CLASSES = {
    "bitmixer": BitMixerTerminal,
    "cipher": CipherTerminal,
    "dummy": DummyTerminal,
    "hash": HashTerminal,
    "main": MainTerminal,
    "maze": MazeTerminal,
    "sys32": Sys32Terminal,
}


@dataclass(frozen=True)
class TerminalSpec:
    terminal_type: str
    positional_args: tuple[Any, ...] = ()
    keyword_args: tuple[tuple[str, Any], ...] = ()

    def to_string(self) -> str:
        if not self.positional_args and not self.keyword_args:
            return self.terminal_type

        parts = [str(arg) for arg in self.positional_args]
        parts.extend(f"{key}={self._format_value(value)}" for key, value in self.keyword_args)
        return f"{self.terminal_type}({','.join(parts)})"

    def keyword_dict(self) -> dict[str, Any]:
        return dict(self.keyword_args)

    @staticmethod
    def _format_value(value: Any) -> str:
        if isinstance(value, str):
            if value.replace("_", "").isalnum():
                return value
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)


@dataclass(frozen=True)
class TerminalLayerSpec:
    terminals: list[TerminalSpec]

    def to_string(self) -> str:
        return "|".join(terminal.to_string() for terminal in self.terminals)


@dataclass(frozen=True)
class TerminalChainSpec:
    layers: tuple[TerminalLayerSpec, ...]

    @property
    def is_main_only(self) -> bool:
        return not self.layers

    def to_string(self) -> str:
        if self.is_main_only:
            return "main"
        return "-".join(layer.to_string() for layer in self.layers)


class TerminalBySpecBuilder:
    def __init__(
        self,
        terminal_classes: Mapping[str, type[BaseTerminal]] | None = None,
    ) -> None:
        self._terminal_classes = dict(terminal_classes or DEFAULT_TERMINAL_CLASSES)
        if "main" not in self._terminal_classes:
            self._terminal_classes["main"] = MainTerminal

    def build(
        self,
        terminal_spec: str | TerminalChainSpec,
        *,
        default_seed: int = 42,
    ) -> BaseTerminal:
        spec = (
            terminal_spec
            if isinstance(terminal_spec, TerminalChainSpec)
            else self.parse_terminal_spec(terminal_spec)
        )

        main_terminal_cls = self._terminal_classes["main"]
        main = main_terminal_cls(f"SYS{len(spec.layers) + 1}", seed=default_seed)
        inner: BaseTerminal = main

        rnd = random.Random(default_seed)

        for index, layer in enumerate(reversed(spec.layers), start=1):
            # Randomly choose a terminal type to use for this layer.
            terminal = rnd.choice(layer.terminals)

            terminal_cls = self._terminal_classes[terminal.terminal_type]
            name = f"SYS{len(spec.layers) - index + 1}"
            seed = default_seed + index
            inner = self._init_terminal(
                terminal_cls,
                terminal,
                name=name,
                nested=inner,
                default_seed=seed,
            )

        return inner

    def parse_terminal_spec(self, raw_spec: str) -> TerminalChainSpec:
        spec = raw_spec.strip()
        if not spec:
            raise ValueError("Terminal spec must not be empty.")

        segments = self._split_top_level(spec, separator="-")
        if segments == ["main"]:
            return TerminalChainSpec(layers=())

        layers: list[TerminalLayerSpec] = []
        for segment in segments:
            layer = self._parse_layer(segment)
            if any(terminal.terminal_type == "main" for terminal in layer.terminals):
                raise ValueError(
                    "'main' may only appear by itself because the leaf terminal is implicit."
                )
            layers.append(layer)

        return TerminalChainSpec(layers=tuple(layers))

    def normalize_terminal_spec(self, raw_spec: str) -> str:
        return self.parse_terminal_spec(raw_spec).to_string()

    @staticmethod
    def _init_terminal(
        terminal_cls: type[BaseTerminal],
        terminal_spec: TerminalSpec,
        *,
        name: str,
        nested: BaseTerminal | None,
        default_seed: int,
    ) -> BaseTerminal:
        signature = inspect.signature(terminal_cls.__init__)
        accepted_params = [
            param.name
            for param in signature.parameters.values()
            if param.name not in {"self", "name", "nested"}
            and param.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        ]

        if len(terminal_spec.positional_args) > len(accepted_params):
            raise ValueError(
                f"Terminal '{terminal_spec.terminal_type}' accepts at most {len(accepted_params)} "
                f"parameter(s), got {len(terminal_spec.positional_args)}."
            )

        kwargs = {
            param_name: value
            for param_name, value in zip(accepted_params, terminal_spec.positional_args, strict=False)
        }
        for key, value in terminal_spec.keyword_args:
            if key not in accepted_params:
                raise ValueError(
                    f"Terminal '{terminal_spec.terminal_type}' does not support parameter '{key}'."
                )
            if key in kwargs:
                raise ValueError(
                    f"Terminal '{terminal_spec.terminal_type}' received parameter '{key}' twice."
                )
            kwargs[key] = value

        if "seed" in accepted_params and "seed" not in kwargs:
            kwargs["seed"] = default_seed

        return terminal_cls(name=name, nested=nested, **kwargs)

    def _parse_layer(self, raw_segment: str) -> TerminalLayerSpec:
        terminal_segments = self._split_top_level(raw_segment, separator="|")
        return TerminalLayerSpec(terminals=[self._parse_terminal(segment) for segment in terminal_segments])

    def _parse_terminal(self, raw_segment: str) -> TerminalSpec:
        segment = raw_segment.strip()
        if not segment:
            raise ValueError("Terminal spec contains an empty segment.")

        if "(" not in segment:
            terminal_type = segment
            self._validate_terminal_type(terminal_type)
            return TerminalSpec(terminal_type=terminal_type)

        if not segment.endswith(")"):
            raise ValueError(f"Malformed segment '{segment}'.")

        terminal_type, raw_args = segment.split("(", 1)
        terminal_type = terminal_type.strip()
        self._validate_terminal_type(terminal_type)

        arg_text = raw_args[:-1].strip()
        positional_args: list[Any] = []
        keyword_args: list[tuple[str, Any]] = []
        if arg_text:
            for token in self._split_top_level(arg_text, separator=","):
                key, value = self._parse_argument(token)
                if key is None:
                    if keyword_args:
                        raise ValueError(
                            f"Positional arguments must come before keyword arguments in '{segment}'."
                        )
                    positional_args.append(value)
                else:
                    keyword_args.append((key, value))

        return TerminalSpec(
            terminal_type=terminal_type,
            positional_args=tuple(positional_args),
            keyword_args=tuple(keyword_args),
        )

    def _parse_argument(self, raw_token: str) -> tuple[str | None, Any]:
        token = raw_token.strip()
        if not token:
            raise ValueError("Empty argument list item.")

        depth = 0
        quote: str | None = None
        for index, char in enumerate(token):
            if quote:
                if char == "\\":
                    continue
                if char == quote:
                    quote = None
                continue
            if char in {"'", '"'}:
                quote = char
                continue
            if char == "=" and depth == 0:
                key = token[:index].strip()
                if not key.isidentifier():
                    raise ValueError(f"Invalid parameter name '{key}'.")
                return key, self._parse_value(token[index + 1 :].strip())
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1

        return None, self._parse_value(token)

    def _parse_value(self, token: str) -> Any:
        if not token:
            raise ValueError("Argument value must not be empty.")

        if token[0] in {"'", '"'}:
            quote = token[0]
            if len(token) < 2 or token[-1] != quote:
                raise ValueError(f"Unterminated string literal {token!r}.")
            body = token[1:-1]
            return body.replace(f"\\{quote}", quote).replace("\\\\", "\\")

        if token in {"true", "false"}:
            return token == "true"

        try:
            return int(token)
        except ValueError:
            pass

        if not token.replace("_", "").isalnum():
            raise ValueError(f"Unsupported argument value '{token}'.")
        return token

    def _split_top_level(self, text: str, *, separator: str) -> list[str]:
        parts: list[str] = []
        current: list[str] = []
        depth = 0
        quote: str | None = None

        for char in text:
            if quote:
                current.append(char)
                if char == quote:
                    quote = None
                elif char == "\\":
                    continue
                continue

            if char in {"'", '"'}:
                quote = char
                current.append(char)
                continue
            if char == "(":
                depth += 1
                current.append(char)
                continue
            if char == ")":
                depth -= 1
                if depth < 0:
                    raise ValueError(f"Malformed terminal spec '{text}'.")
                current.append(char)
                continue
            if char == separator and depth == 0:
                parts.append("".join(current).strip())
                current = []
                continue
            current.append(char)

        if quote or depth != 0:
            raise ValueError(f"Malformed terminal spec '{text}'.")

        parts.append("".join(current).strip())
        return parts

    def _validate_terminal_type(self, terminal_type: str) -> None:
        if terminal_type not in self._terminal_classes:
            supported = ", ".join(sorted(self._terminal_classes))
            raise ValueError(
                f"Unknown terminal type '{terminal_type}'. Supported: {supported}."
            )


def normalize_terminal_spec(raw_spec: str) -> str:
    return TerminalBySpecBuilder().normalize_terminal_spec(raw_spec)

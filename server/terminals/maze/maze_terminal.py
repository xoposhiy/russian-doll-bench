"""Weighted-grid XOR wrapper terminal."""

from __future__ import annotations

import heapq
import random
import string

from server.base_terminal import BaseTerminal

_HEX_ALPHABET = set(string.hexdigits)
_PHRASE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_MOVE_DIRS = {
    "U": (-1, 0),
    "D": (1, 0),
    "L": (0, -1),
    "R": (0, 1),
}


def _normalize_hex(text: str) -> str | None:
    token = text.strip()
    if not token or any(ch not in _HEX_ALPHABET for ch in token):
        return None
    if len(token) % 2 == 1:
        token += "0"
    return token.lower()


def _derive_phrase(seed: int) -> str:
    rng = random.Random(seed ^ 0xA617_2026)
    return "".join(rng.choice(_PHRASE_ALPHABET) for _ in range(6))


def _xor_hex_with_key(payload_hex: str, key_bytes: bytes) -> str:
    data = bytes.fromhex(payload_hex)
    xored = bytes(byte ^ key_bytes[index % len(key_bytes)] for index, byte in enumerate(data))
    return xored.hex()


def _encode_plaintext(plaintext: str, key_bytes: bytes) -> str:
    return _xor_hex_with_key(plaintext.encode("latin-1").hex(), key_bytes)


def _decode_hex_payload(payload_hex: str, key_bytes: bytes) -> tuple[str | None, str]:
    normalized = _normalize_hex(payload_hex)
    if normalized is None:
        return None, "Expected hex bytes, for example `01fe1a`."
    decoded_hex = _xor_hex_with_key(normalized, key_bytes)
    try:
        return bytes.fromhex(decoded_hex).decode("latin-1"), ""
    except UnicodeDecodeError:
        return None, "Decoded bytes are not valid Latin-1 text."


def _grid_key_from_path(grid: tuple[str, ...]) -> bytes:
    digits = _collect_weighted_route_digits(grid)
    joined = "".join(digits)
    if not joined:
        return b"\x00"
    if len(joined) % 2 == 1:
        joined += "0"
    return bytes.fromhex(joined)


def _collect_weighted_route_digits(grid: tuple[str, ...]) -> list[str]:
    path, _ = _solve_weighted_route(grid)
    return [grid[row][col] for row, col in path]


def _solve_weighted_route(grid: tuple[str, ...]) -> tuple[list[tuple[int, int]], str]:
    if not grid or not grid[0]:
        return [(0, 0)], ""

    rows = len(grid)
    cols = len(grid[0])
    start = (0, 0)
    target = (rows - 1, cols - 1)

    queue: list[tuple[int, int, int, int]] = []
    heapq.heappush(queue, (0, 0, 0, 0))
    best_cost: dict[tuple[int, int], int] = {start: 0}
    best_steps: dict[tuple[int, int], int] = {start: 0}
    prev: dict[tuple[int, int], tuple[int, int] | None] = {start: None}

    while queue:
        cost, steps, row, col = heapq.heappop(queue)
        pos = (row, col)
        if cost != best_cost[pos] or steps != best_steps[pos]:
            continue
        if pos == target:
            break
        for move in "DRUL":
            dr, dc = _MOVE_DIRS[move]
            nr = row + dr
            nc = col + dc
            if nr < 0 or nr >= rows or nc < 0 or nc >= cols:
                continue
            nxt = (nr, nc)
            next_cost = cost + int(grid[nr][nc], 16)
            next_steps = steps + 1
            current_cost = best_cost.get(nxt)
            current_steps = best_steps.get(nxt)
            if current_cost is None or next_cost < current_cost or (
                next_cost == current_cost and next_steps < current_steps
            ):
                best_cost[nxt] = next_cost
                best_steps[nxt] = next_steps
                prev[nxt] = pos
                heapq.heappush(queue, (next_cost, next_steps, nr, nc))

    path: list[tuple[int, int]] = []
    node: tuple[int, int] | None = target
    while node is not None:
        path.append(node)
        node = prev[node]
    path.reverse()
    moves: list[str] = []
    for current, nxt in zip(path, path[1:], strict=False):
        dr = nxt[0] - current[0]
        dc = nxt[1] - current[1]
        for move, (mdr, mdc) in _MOVE_DIRS.items():
            if (dr, dc) == (mdr, mdc):
                moves.append(move)
                break
    return path, "".join(moves)


class _MapSequence:
    def __init__(
        self,
        *,
        seed: int,
        rows: int,
        cols: int,
    ) -> None:
        self._rng = random.Random(seed)
        self._rows = rows
        self._cols = cols
        self._index = 0

    @property
    def index(self) -> int:
        return self._index

    def advance(self) -> tuple[str, ...]:
        grid = self._make_grid()
        self._index += 1
        return grid

    def _make_grid(self) -> tuple[str, ...]:
        best_grid: tuple[str, ...] | None = None
        best_score: tuple[int, int] | None = None
        for _ in range(10):
            grid = self._make_random_grid()
            _, moves = _solve_weighted_route(grid)
            score = (1 if any(move in {"L", "U"} for move in moves) else 0, len(moves))
            if best_score is None or score > best_score:
                best_grid = grid
                best_score = score
        assert best_grid is not None
        return best_grid

    def _make_random_grid(self) -> tuple[str, ...]:
        return tuple(
            "".join(self._rng.choice("0123456789abcdef") for _ in range(self._cols))
            for _ in range(self._rows)
        )


class MazeTerminal(BaseTerminal):
    """Wrapper terminal based on weighted-grid shortest paths."""

    def __init__(self, name: str, seed: int, nested=None) -> None:
        super().__init__(name=name, seed=seed, nested=nested)
        self._activation_phrase = _derive_phrase(seed)
        rows, cols = self._pick_grid_shape(seed)
        self._activation_maps = _MapSequence(
            seed=seed ^ 0x1155AA,
            rows=rows,
            cols=cols,
        )
        self._send_maps = _MapSequence(
            seed=seed ^ 0x77CC44,
            rows=rows,
            cols=cols,
        )
        self._activation_map = self._activation_maps.advance()
        self._send_map = self._send_maps.advance()

    def _pick_grid_shape(self, seed: int) -> tuple[int, int]:
        rng = random.Random(seed ^ 0x6D4A2E)
        return rng.choice(
            (
                (5, 4),
                (5, 6),
                (7, 4),
                (7, 6),
            )
        )

    def get_welcome_message(self) -> str:
        return "Shortest path XOR Terminal is ready! Use HELP to get more info"

    def send(self, payload: str) -> str:
        raw = payload.strip()
        if not raw:
            return self.get_welcome_message()

        parts = raw.split(None, 1)
        command = parts[0].upper()

        if command == "HELP":
            return self._help_text()
        if command == "MAP":
            return self._render_state(status="MAP")
        if command == "ACTIVATE":
            if len(parts) < 2 or not parts[1].strip():
                return f"[{self._terminal_id}] ACTIVATE requires <hex>."
            return self._handle_activate(parts[1].strip())
        if command == "SEND":
            if len(parts) < 2 or not parts[1].strip():
                return f"[{self._terminal_id}] SEND requires <hex>."
            return self._handle_send(parts[1].strip())

        return f"[{self._terminal_id}] Unknown command {parts[0]!r}. Use HELP."

    def _handle_activate(self, payload_hex: str) -> str:
        key = _grid_key_from_path(self._activation_map)
        decoded, error = _decode_hex_payload(payload_hex, key)
        if decoded is None:
            return self._render_state(status=f"ACTIVATE failed: {error}")
        if decoded != self._activation_phrase:
            self._activation_map = self._activation_maps.advance()
            return self._render_state(
                status=(
                    f"ACTIVATE failed: decoded {decoded!r}; expected activation phrase. "
                    "Send the shown phrase XOR-encoded with the current route-key. Activation map rotated."
                )
            )

        self._online = True
        if self._nested is None:
            child_line = "offline"
        else:
            child_line = _encode_plaintext(self._nested.get_welcome_message(), _grid_key_from_path(self._send_map))
        return self._render_state(status="UPLINK ONLINE", child_hex=child_line)

    def _handle_send(self, payload_hex: str) -> str:
        if not self._online:
            return self._render_state(status="SEND blocked: uplink locked.")

        key = _grid_key_from_path(self._send_map)
        decoded, error = _decode_hex_payload(payload_hex, key)
        if decoded is None:
            return self._render_state(status=f"SEND failed: {error}")

        if self._nested is None:
            response = "offline"
        else:
            try:
                response = self.dispatch_child(decoded)
            except RuntimeError:
                response = "offline"

        encoded_response = _encode_plaintext(response, key)
        self._send_map = self._send_maps.advance()
        return self._render_state(status="SENT", child_hex=encoded_response)

    def _help_text(self) -> str:
        return (
            f"[{self._terminal_id}] Commands:\n"
            "  ACTIVATE <hex>  - unlock uplink\n"
            "  SEND <hex>      - communicate with uplink\n"
            "  MAP             - print current activation map, send map, phrase, and state\n"
            "  HELP            - commands and rules\n"
            "Rules:\n"
            "  Maps show movement cost of every cell as a hex digit.\n"
            "  Shortest path from top-left to bottom-right defines the XOR key.\n"
            "  Every two nibbles from that route form one XOR-key byte.\n"
            "  Both SEND and ACTIVATE decode the provided hex, XOR it with the route-key, and then interpret the result.\n"
            "  Failed ACTIVATE rotates the activation terrain.\n"
            "  Successful SEND rotates the send terrain."
        )

    def _render_state(self, *, status: str, child_hex: str | None = None) -> str:
        lines = [
            f"[{self._terminal_id}] MAZE",
            f"uplink: {'online' if self._online else 'locked'}",
            f"activation-phrase: {self._activation_phrase}",
            f"activation-map #{self._activation_maps.index}",
            *self._activation_map,
            f"send-map #{self._send_maps.index}",
            *self._send_map,
            f"status: {status}",
        ]
        if child_hex is not None:
            lines.append(f"uplink-response: {child_hex}")
        return "\n".join(lines)

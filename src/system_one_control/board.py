from __future__ import annotations

from dataclasses import dataclass, replace

WALL, FLOOR, AGENT, GOAL, KEY, DOOR = "#", ".", "A", "G", "K", "D"
SYMBOL_NAMES = {
    WALL: "wall",
    FLOOR: "floor",
    AGENT: "you",
    GOAL: "goal",
    KEY: "key",
    DOOR: "locked door",
}


@dataclass(frozen=True)
class Position:
    x: int
    y: int

    def moved(self, dx: int, dy: int) -> Position:
        return Position(self.x + dx, self.y + dy)

    def __str__(self) -> str:
        return f"({self.x}, {self.y})"


@dataclass(frozen=True)
class Board:
    """The map without the agent, where the agent stands, and what it carries."""

    rows: tuple[str, ...]
    agent: Position
    holding: tuple[str, ...] = ()

    @classmethod
    def parse(cls, text: str) -> Board:
        rows = [line.strip() for line in text.strip().splitlines()]
        if len({len(row) for row in rows}) != 1:
            raise ValueError("every row of a map must be the same width")
        unknown = set("".join(rows)) - SYMBOL_NAMES.keys()
        if unknown:
            raise ValueError(f"unknown map symbols: {sorted(unknown)}")
        agents = [
            Position(x, y)
            for y, row in enumerate(rows)
            for x, cell in enumerate(row)
            if cell == AGENT
        ]
        if len(agents) != 1:
            raise ValueError(f"a map needs exactly one {AGENT}, found {len(agents)}")
        agent = agents[0]
        rows[agent.y] = rows[agent.y].replace(AGENT, FLOOR)
        return cls(tuple(rows), agent)

    def at(self, position: Position) -> str:
        if 0 <= position.y < len(self.rows) and 0 <= position.x < len(self.rows[position.y]):
            return self.rows[position.y][position.x]
        return WALL

    def find(self, symbol: str) -> tuple[Position, ...]:
        return tuple(
            Position(x, y)
            for y, row in enumerate(self.rows)
            for x, cell in enumerate(row)
            if cell == symbol
        )

    def with_cell(self, position: Position, symbol: str) -> Board:
        rows = list(self.rows)
        row = rows[position.y]
        rows[position.y] = row[: position.x] + symbol + row[position.x + 1 :]
        return replace(self, rows=tuple(rows))

    def with_agent(self, position: Position) -> Board:
        return replace(self, agent=position)

    def pick_up(self, item: str) -> Board:
        return replace(self, holding=(*self.holding, item))

    def draw(self) -> str:
        return "\n".join(self.with_cell(self.agent, AGENT).rows)

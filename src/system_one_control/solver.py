from __future__ import annotations

from collections import deque

from system_one_control.board import Board
from system_one_control.rules import Rules


class Solver:
    """Exact shortest paths by breadth-first search over boards."""

    def __init__(self, rules: Rules) -> None:
        self.rules = rules

    def distance(self, board: Board) -> int | None:
        """Fewest moves to win from this board, or None if the goal cannot be reached."""
        frontier = deque([(board, 0)])
        seen = {board}
        while frontier:
            current, moves = frontier.popleft()
            if self.rules.is_won(current):
                return moves
            for move in self.rules.moves(current):
                after = self.rules.apply(current, move)
                if after not in seen:
                    seen.add(after)
                    frontier.append((after, moves + 1))
        return None

    def best_moves(self, board: Board) -> tuple[str, ...]:
        """Every move that starts a shortest path, ties included."""
        distance = self.distance(board)
        if not distance:
            return ()
        return tuple(
            move.name
            for move in self.rules.moves(board)
            if self.distance(self.rules.apply(board, move)) == distance - 1
        )

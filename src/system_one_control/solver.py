from __future__ import annotations

from collections import deque

from system_one_control.board import Board
from system_one_control.rules import Rules


class Solver:
    """Exact shortest paths by breadth-first search over boards."""

    def __init__(self, rules: Rules) -> None:
        self.rules = rules

    def moves_to_goal(self, board: Board) -> int | None:
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

    def distances(self, board: Board) -> dict[Board, int]:
        """The fewest moves to win from every board reachable from this one that can win.

        One search forward to map every move, then one back from the winning boards: much
        cheaper than a search per board when there are many moves, as under sequence rules.
        """
        came_from: dict[Board, list[Board]] = {board: []}
        frontier = deque([board])
        while frontier:
            current = frontier.popleft()
            if self.rules.is_won(current):
                continue  # the game ends here
            for move in self.rules.moves(current):
                after = self.rules.apply(current, move)
                if after not in came_from:
                    came_from[after] = []
                    frontier.append(after)
                came_from[after].append(current)
        found = {b: 0 for b in came_from if self.rules.is_won(b)}
        back = deque(found)
        while back:
            current = back.popleft()
            for before in came_from[current]:
                if before not in found:
                    found[before] = found[current] + 1
                    back.append(before)
        return found

    def best_moves(self, board: Board) -> tuple[str, ...]:
        """Every move that starts a shortest path, ties included."""
        distances = self.distances(board)
        distance = distances.get(board)
        if not distance:
            return ()
        return tuple(
            move.name
            for move in self.rules.moves(board)
            if distances.get(self.rules.apply(board, move)) == distance - 1
        )

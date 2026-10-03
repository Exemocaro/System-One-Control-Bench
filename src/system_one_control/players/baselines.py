"""Players that read the board: fixed, perfect, or heading for the next target."""

from __future__ import annotations

import random
from collections.abc import Sequence

from system_one_control.players.base import Choice, Player, Turn
from system_one_control.world import Board, CompassRules, Move, Rules, Solver, next_target


class RandomPlayer(Player):
    def __init__(self, seed: int = 0) -> None:
        self._rng = random.Random(seed)

    def choose(self, turn: Turn) -> Choice:
        return Choice(self._rng.choice(turn.request.options).move)


class ScriptedPlayer(Player):
    """Plays a fixed list of moves, then gives up. For examples and tests."""

    def __init__(self, moves: Sequence[str | None]) -> None:
        self._moves = iter(moves)

    def choose(self, turn: Turn) -> Choice:
        move = next(self._moves, None)
        return Choice(move, error=None if move else "out of scripted moves")


class SolverPlayer(Player):
    """Plays perfectly by searching the real board."""

    plays_argmax = True  # every best move shares the top probability

    def __init__(self) -> None:
        # The distances from the first board of a game cover every later one.
        self._rules: Rules | None = None
        self._distances: dict[Board, int] = {}

    def choose(self, turn: Turn) -> Choice:
        solver = Solver(turn.rules)
        if turn.rules is not self._rules or turn.board not in self._distances:
            self._rules, self._distances = turn.rules, solver.distances(turn.board)
        best = solver.best_moves(turn.board, self._distances)
        if not best:
            return Choice(None, error="the goal cannot be reached")
        return Choice(best[0], {move: 1 / len(best) for move in best})


class GreedyPlayer(Player):
    """Steps straight toward the key, then the door, then the goal, and never plans.

    It shows what heading for the next target is worth on its own. It ignores walls, and it
    breaks ties by the rules' order of moves, so the option shuffle never changes its game.
    Compass rules only.
    """

    avoids_blocked_moves = False

    def choose(self, turn: Turn) -> Choice:
        return Choice(self.pick(turn.board, turn.rules))

    def pick(self, board: Board, rules: Rules) -> str:
        moves = rules.moves(board)
        if self.avoids_blocked_moves:
            moves = tuple(m for m in moves if rules.apply(board, m) != board) or moves
        _, target = next_target(board)

        def distance_after(move: Move) -> int:
            there = board.agent.moved(*CompassRules.STEPS[move.name])
            return abs(there.x - target.x) + abs(there.y - target.y)

        return min(moves, key=distance_after).name


class WallAwareGreedyPlayer(GreedyPlayer):
    """Greedy, but never picks a move that would leave it where it stands."""

    avoids_blocked_moves = True

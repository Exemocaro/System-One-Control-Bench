from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace

from system_one_control.players import Choice, Player, Turn
from system_one_control.prompts import Condition, Request
from system_one_control.puzzles import Puzzle
from system_one_control.world import Board, Rules, Solver


@dataclass(frozen=True)
class Step:
    number: int
    before: Board
    request: Request
    choice: Choice
    best_moves: tuple[str, ...]
    after: Board
    seconds: float

    @property
    def optimal(self) -> bool:
        return self.choice.move in self.best_moves


class Game:
    """One player working through one puzzle, a move at a time."""

    def __init__(self, puzzle: Puzzle, player: Player, condition: Condition) -> None:
        self.puzzle = puzzle
        self.player = player
        self.condition = condition
        self.solver = Solver(puzzle.rules)
        self.board = puzzle.board
        # Worked out once: the distances from the start cover every board the game can reach.
        self._distances = self.solver.distances(self.board)
        # Counted in the moves a level is counted in, which may be shorter than these rules'.
        self._step_distances = Solver(puzzle.rules.step_rules()).distances(self.board)
        self.steps: list[Step] = []

    @property
    def rules(self) -> Rules:
        return self.puzzle.rules

    @property
    def won(self) -> bool:
        return self.rules.is_won(self.board)

    @property
    def closest(self) -> int | None:
        """The fewest moves to the goal from any board reached so far, the start included.

        Counted in the moves a level is counted in, so it compares across rules, and taking in
        every board a move passed through, not only the one it ended on.
        """
        boards = {self.puzzle.board}
        for step in self.steps:
            move = self.rules.find_move(step.before, step.choice.move)
            if move is not None:
                boards.update(self.rules.passes(step.before, move))
        distances = (self._step_distances.get(board) for board in boards)
        return min((d for d in distances if d is not None), default=None)

    def best_moves(self, board: Board) -> tuple[str, ...]:
        """Every move from a board of this game that starts a shortest path."""
        return self.solver.best_moves(board, self._distances)

    @property
    def is_over(self) -> bool:
        failed = bool(self.steps) and self.steps[-1].choice.move is None
        return self.won or failed or len(self.steps) >= self.puzzle.max_moves

    def next_request(self) -> Request:
        memory = [
            f"{step.choice.move}: {self.rules.describe_outcome(step.before, step.after)}"
            for step in self.steps
        ]
        seed = f"{self.puzzle.name}:{len(self.steps) + 1}"
        return self.condition.render(self.board, self.rules, shuffle_seed=seed, memory=memory)

    def step(self) -> Step:
        if self.is_over:
            raise RuntimeError("the game is over")
        request = self.next_request()
        started = time.perf_counter()
        try:
            choice = self.player.choose(Turn(self.board, self.rules, request))
        except Exception as error:  # a player that fails has failed this move, not the run
            choice = Choice(None, error=f"{type(error).__name__}: {error}")
        seconds = time.perf_counter() - started

        move = self.rules.find_move(self.board, choice.move)
        if move is None and choice.move is not None:
            choice = replace(choice, move=None, error=f"{choice.move!r} is not an allowed move")
        after = self.board if move is None else self.rules.apply(self.board, move)

        step = Step(
            number=len(self.steps) + 1,
            before=self.board,
            request=request,
            choice=choice,
            best_moves=self.best_moves(self.board),
            after=after,
            seconds=seconds,
        )
        self.steps.append(step)
        self.board = after
        return step

    def play(self, stop: threading.Event | None = None) -> list[Step]:
        """Play to the end, or until `stop` is set, which takes effect between moves."""
        while not self.is_over and not (stop and stop.is_set()):
            self.step()
        return self.steps

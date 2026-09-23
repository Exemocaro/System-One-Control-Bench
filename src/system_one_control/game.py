from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace

from system_one_control.board import Board
from system_one_control.conditions import Condition
from system_one_control.players import Choice, Player, Turn
from system_one_control.request import Request
from system_one_control.rules import Rules
from system_one_control.scenario import Scenario
from system_one_control.solver import Solver


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
    """One player working through one scenario, a move at a time."""

    def __init__(self, scenario: Scenario, player: Player, condition: Condition) -> None:
        self.scenario = scenario
        self.player = player
        self.condition = condition
        self.solver = Solver(scenario.rules)
        self.distance = Solver(scenario.rules.step_rules())  # counts the level's own moves
        self.board = scenario.board
        self.steps: list[Step] = []

    @property
    def rules(self) -> Rules:
        return self.scenario.rules

    @property
    def won(self) -> bool:
        return self.rules.is_won(self.board)

    @property
    def closest(self) -> int | None:
        """The fewest moves to the goal from any board reached so far, the start included.

        Counted in the moves a level is counted in, so it compares across rules.
        """
        boards = {self.scenario.board, *(step.after for step in self.steps)}
        distances = (self.distance.moves_to_goal(board) for board in boards)
        return min((d for d in distances if d is not None), default=None)

    @property
    def is_over(self) -> bool:
        failed = bool(self.steps) and self.steps[-1].choice.move is None
        return self.won or failed or len(self.steps) >= self.scenario.max_moves

    def next_request(self) -> Request:
        history = [
            f"{step.choice.move}: {self.rules.describe_outcome(step.before, step.after)}"
            for step in self.steps
        ]
        seed = f"{self.scenario.name}:{len(self.steps) + 1}"
        return self.condition.render(self.board, self.rules, shuffle_seed=seed, history=history)

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
            best_moves=self.solver.best_moves(self.board),
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

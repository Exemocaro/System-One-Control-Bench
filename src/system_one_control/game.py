from __future__ import annotations

import time
from dataclasses import dataclass, replace

from system_one_control.board import Board
from system_one_control.players import Choice, Player, Turn
from system_one_control.prompt import Prompt, Request, describe_outcome
from system_one_control.rules import Rules
from system_one_control.scenario import Scenario
from system_one_control.solver import Solver


@dataclass(frozen=True)
class Step:
    number: int
    board: Board
    request: Request
    choice: Choice
    best_moves: tuple[str, ...]
    after: Board
    seconds: float

    @property
    def correct(self) -> bool:
        return self.choice.move in self.best_moves


class Game:
    """One player working through one scenario, a move at a time."""

    def __init__(self, scenario: Scenario, player: Player, prompt: Prompt) -> None:
        self.scenario = scenario
        self.player = player
        self.prompt = prompt
        self.solver = Solver(scenario.rules)
        self.board = scenario.board
        self.steps: list[Step] = []

    @property
    def rules(self) -> Rules:
        return self.scenario.rules

    @property
    def won(self) -> bool:
        return self.rules.is_won(self.board)

    @property
    def over(self) -> bool:
        failed = bool(self.steps) and self.steps[-1].choice.move is None
        return self.won or failed or len(self.steps) >= self.scenario.max_moves

    def next_request(self) -> Request:
        history = [
            f"{step.choice.move}: {describe_outcome(step.board, step.after, self.rules)}"
            for step in self.steps
        ]
        seed = f"{self.scenario.name}:{len(self.steps) + 1}"
        return self.prompt.render(self.board, self.rules, shuffle_seed=seed, history=history)

    def step(self) -> Step:
        if self.over:
            raise RuntimeError("the game is over")
        request = self.next_request()
        started = time.perf_counter()
        choice = self.player.choose(Turn(self.board, self.rules, request))
        seconds = time.perf_counter() - started

        move = self.rules.find_move(self.board, choice.move)
        if move is None and choice.move is not None:
            choice = replace(choice, move=None, error=f"{choice.move!r} is not an allowed move")
        after = self.board if move is None else self.rules.apply(self.board, move)

        step = Step(
            number=len(self.steps) + 1,
            board=self.board,
            request=request,
            choice=choice,
            best_moves=self.solver.best_moves(self.board),
            after=after,
            seconds=seconds,
        )
        self.steps.append(step)
        self.board = after
        return step

    def play(self) -> list[Step]:
        while not self.over:
            self.step()
        return self.steps

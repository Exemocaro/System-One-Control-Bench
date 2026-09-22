from system_one_control.board import Board
from system_one_control.players import Choice, Player, Turn
from system_one_control.prompt import Prompt
from system_one_control.rules import CompassRules
from system_one_control.scenario import Scenario

PROMPT = Prompt(name="plain", description="", state="{map}", question="Which way?")


def scenario(text: str, moves_to_goal: int, best: tuple[str, ...], max_moves: int = 20) -> Scenario:
    return Scenario(
        name="test",
        description="",
        board=Board.parse(text),
        rules=CompassRules(),
        moves_to_goal=moves_to_goal,
        best_first_moves=best,
        max_moves=max_moves,
    )


class AlwaysPlayer(Player):
    """Always answers the same move, allowed or not."""

    name = "always"

    def __init__(self, move: str | None) -> None:
        self.move = move

    def choose(self, turn: Turn) -> Choice:
        return Choice(self.move)

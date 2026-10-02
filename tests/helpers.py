from system_one_control.board import Board
from system_one_control.conditions import CONDITIONS
from system_one_control.players import Choice, Player, Turn
from system_one_control.rules import CompassRules
from system_one_control.scenario import Scenario

MAP = CONDITIONS["map"]


def scenario(text: str, moves_to_goal: int) -> Scenario:
    return Scenario(
        name="test",
        description="",
        board=Board.parse(text),
        rules=CompassRules(),
        moves_to_goal=moves_to_goal,
    )


class AlwaysPlayer(Player):
    """Always answers the same move, allowed or not."""

    def __init__(self, move: str | None) -> None:
        self.move = move

    def choose(self, turn: Turn) -> Choice:
        return Choice(self.move)

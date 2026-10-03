from system_one_control.players import Choice, Player, Turn
from system_one_control.prompts import CONDITIONS
from system_one_control.puzzles import Puzzle
from system_one_control.world import Board, CompassRules

MAP = CONDITIONS["map"]


def puzzle(text: str, level: int) -> Puzzle:
    return Puzzle(
        name="test",
        description="",
        board=Board.parse(text),
        rules=CompassRules(),
        level=level,
    )


def turn(text: str) -> Turn:
    board = Board.parse(text)
    return Turn(board, CompassRules(), MAP.render(board, CompassRules()))


def option_for(turn: Turn, move: str) -> str:
    return next(option.id for option in turn.request.options if option.move == move)


class AlwaysPlayer(Player):
    """Always answers the same move, allowed or not."""

    def __init__(self, move: str | None) -> None:
        self.move = move

    def choose(self, turn: Turn) -> Choice:
        return Choice(self.move)

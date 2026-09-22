import pytest

from system_one_control.board import Board, Position
from system_one_control.rules import CompassRules, make_rules

rules = CompassRules()


def move(board: Board, name: str) -> Board:
    return rules.apply(board, rules.find_move(board, name))


def test_there_are_always_four_moves():
    board = Board.parse("###\n#A#\n###")
    assert [m.name for m in rules.moves(board)] == ["north", "south", "east", "west"]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("north", Position(2, 1)),
        ("south", Position(2, 3)),
        ("east", Position(3, 2)),
        ("west", Position(1, 2)),
    ],
)
def test_each_move_goes_one_cell_in_its_direction(name, expected):
    board = Board.parse("#####\n#...#\n#.A.#\n#...#\n#####")
    assert move(board, name).agent == expected


def test_a_wall_blocks_the_move():
    board = Board.parse("###\n#A#\n###")
    assert move(board, "east") == board


def test_stepping_onto_the_key_picks_it_up():
    after = move(Board.parse("####\n#AK#\n####"), "east")
    assert after.holding == ("key",)
    assert after.at(after.agent) == "."


def test_a_locked_door_blocks_you_without_the_key():
    board = Board.parse("####\n#AD#\n####")
    assert move(board, "east") == board


def test_the_key_opens_the_door_and_you_step_through():
    after = move(move(Board.parse("#####\n#AKD#\n#####"), "east"), "east")
    assert after.agent == Position(3, 1)
    assert after.at(after.agent) == "."


def test_standing_on_the_goal_wins():
    board = Board.parse("####\n#AG#\n####")
    assert not rules.is_won(board)
    assert rules.is_won(move(board, "east"))


def test_compass_rules_describe_what_is_next_to_you():
    board = Board.parse("#####\n#.D.#\n#KAG#\n#####")
    around = rules.facts(board)["around"]
    assert around == (
        "North of you is the locked door. South of you is a wall. "
        "East of you is the goal. West of you is the key."
    )


def test_compass_rules_say_where_things_are_relative_to_you():
    board = Board.parse("######\n#A...#\n#..K.#\n#...G#\n######")
    assert rules.facts(board)["relative"] == (
        "The goal is 3 east and 2 south of you. The key is 2 east and 1 south of you."
    )


def test_a_carried_key_is_no_longer_placed_relative_to_you():
    board = move(Board.parse("#####\n#AKG#\n#####"), "east")
    assert rules.facts(board)["relative"] == "The goal is 1 east of you."


def test_rules_are_found_by_name():
    assert isinstance(make_rules("compass"), CompassRules)
    with pytest.raises(ValueError, match="unknown rules"):
        make_rules("chess")

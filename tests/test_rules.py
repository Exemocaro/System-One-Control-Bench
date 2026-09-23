import pytest

from system_one_control.board import Board, Position
from system_one_control.rules import CompassRules, ThreeMoveRules, TwoMoveRules, make_rules

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
    around = rules.describe_surroundings(board).splitlines()[0]
    assert around == (
        "North of you is the locked door. South of you is a wall. "
        "East of you is the goal. West of you is the key."
    )


def test_compass_rules_say_where_things_are_relative_to_you():
    board = Board.parse("######\n#A...#\n#..K.#\n#...G#\n######")
    assert rules.describe_surroundings(board).splitlines()[1] == (
        "The goal is 3 east and 2 south of you. The key is 2 east and 1 south of you."
    )


def test_a_carried_key_is_no_longer_placed_relative_to_you():
    board = move(Board.parse("#####\n#AKG#\n#####"), "east")
    assert rules.describe_surroundings(board).splitlines()[1] == "The goal is 1 east of you."


@pytest.mark.parametrize(
    ("text", "target"),
    [
        ("######\n#AKDG#\n######", "the key K at (2, 1)"),
        ("#####\n#ADG#\n#####", "the locked door D at (2, 1)"),
        ("####\n#AG#\n####", "the goal G at (2, 1)"),
    ],
)
def test_the_next_target_is_the_key_then_the_door_then_the_goal(text, target):
    assert rules.describe_next_target(Board.parse(text)) == target


@pytest.mark.parametrize(
    ("before", "name", "expected"),
    [
        ("#####\n#A.G#\n#####", "east", "you move to (2, 1)"),
        ("#####\n#A.G#\n#####", "west", "blocked, you stay at (1, 1)"),
        ("####\n#AK#\n####", "east", "you move to (2, 1) and pick up the key"),
        ("####\n#AG#\n####", "east", "you move to (2, 1) and reach the goal"),
    ],
)
def test_outcomes_are_described_in_plain_words(before, name, expected):
    board = Board.parse(before)
    assert rules.describe_outcome(board, move(board, name)) == expected


def test_unlocking_the_door_is_described():
    board = Board.parse("####\n#AD#\n####").pick_up("key")
    assert (
        rules.describe_outcome(board, move(board, "east"))
        == "you move to (2, 1) and unlock the door"
    )


def test_rules_are_found_by_name():
    assert isinstance(make_rules("compass"), CompassRules)
    with pytest.raises(ValueError, match="unknown rules"):
        make_rules("chess")


two = TwoMoveRules()
three = ThreeMoveRules()


def sequence(rules, text: str, name: str) -> Board:
    board = Board.parse(text)
    return rules.apply(board, rules.find_move(board, name))


def test_a_sequence_move_is_every_ordering_of_compass_moves():
    board = Board.parse("###\n#A#\n###")
    assert len(two.moves(board)) == 16
    assert len(three.moves(board)) == 64
    assert two.find_move(board, "north,north") is not None
    assert two.find_move(board, "east,north").description == "move east (right), then north (up)"


def test_a_sequence_takes_its_steps_in_order():
    assert sequence(two, "#####\n#...#\n#A..#\n#####", "north,east").agent == Position(2, 1)
    assert sequence(three, "######\n#A...#\n######", "east,east,west").agent == Position(2, 1)


def test_a_blocked_step_is_wasted_and_the_rest_are_still_taken():
    assert sequence(two, "#####\n#A..#\n#####", "north,east").agent == Position(2, 1)


def test_reaching_the_goal_ends_the_sequence_there():
    after = sequence(three, "######\n#AG..#\n######", "east,east,east")
    assert after.agent == Position(2, 1)
    assert two.is_won(after)


def test_a_sequence_can_pick_up_the_key_and_open_the_door():
    after = sequence(two, "#####\n#AKD#\n#####", "east,east")
    assert after.agent == Position(3, 1)
    assert after.holding == ("key",)


@pytest.mark.parametrize(
    ("before", "name", "expected"),
    [
        ("#####\n#A..#\n#####", "east,east", "you end at (3, 1)"),
        ("#####\n#A..#\n#####", "east,west", "you end where you started, at (1, 1)"),
        ("#####\n#A..#\n#####", "north,west", "you end where you started, at (1, 1)"),
        ("#####\n#AK.#\n#####", "east,east", "you end at (3, 1) and pick up the key"),
        ("#####\n#AG.#\n#####", "east,east", "you end at (2, 1) and reach the goal"),
    ],
)
def test_a_sequence_is_described_by_where_it_ends_and_what_happened(before, name, expected):
    board = Board.parse(before)
    assert two.describe_outcome(board, two.apply(board, two.find_move(board, name))) == expected


@pytest.mark.parametrize(("level", "two_moves", "three_moves"), [(1, 1, 1), (4, 2, 2), (10, 5, 4)])
def test_a_level_needs_its_distance_over_the_sequence_length_rounded_up(
    level, two_moves, three_moves
):
    assert rules.moves_for(level) == level
    assert two.moves_for(level) == two_moves
    assert three.moves_for(level) == three_moves


def test_sequence_rules_count_levels_in_compass_moves():
    assert isinstance(two.step_rules(), CompassRules)
    assert rules.step_rules() is rules


def test_sequence_rules_are_found_by_name():
    assert isinstance(make_rules("two-moves"), TwoMoveRules)
    assert isinstance(make_rules("three-moves"), ThreeMoveRules)

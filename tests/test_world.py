import pytest

from system_one_control.puzzles import load_puzzles
from system_one_control.world import (
    Board,
    CompassRules,
    Position,
    Solver,
    ThreeMoveRules,
    TwoMoveRules,
    UpToThreeMoveRules,
    UpToTwoMoveRules,
    make_rules,
)


def test_parsing_finds_the_agent_and_leaves_floor_under_it():
    board = Board.parse("#####\n#AG.#\n#####")
    assert board.agent == Position(1, 1)
    assert board.at(Position(1, 1)) == "."


def test_parsing_draws_the_agent_back_on_the_map():
    assert Board.parse("#####\n#AG.#\n#####").draw() == "#####\n#AG.#\n#####"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("#####\n#.G.#\n#####", "exactly one A"),
        ("#####\n#AX.#\n#####", "unknown"),
        ("#####\n#AG#\n#####", "same width"),
    ],
    ids=["a map with no agent", "an unknown symbol", "rows of different widths"],
)
def test_a_map_that_cannot_be_read_is_refused(text, message):
    with pytest.raises(ValueError, match=message):
        Board.parse(text)


def test_a_cell_outside_the_map_counts_as_wall():
    assert Board.parse("#####\n#AG.#\n#####").at(Position(-1, 0)) == "#"


def test_find_lists_every_cell_with_a_symbol():
    assert Board.parse("#####\n#AG.#\n#####").find("G") == (Position(2, 1),)


def test_the_compass_rules_always_offer_the_same_four_moves():
    board = Board.parse("###\n#A#\n###")
    assert [move.name for move in CompassRules().moves(board)] == ["north", "south", "east", "west"]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("north", (2, 1)),
        ("south", (2, 3)),
        ("east", (3, 2)),
        ("west", (1, 2)),
    ],
    ids=["north goes one cell up", "south goes down", "east goes right", "west goes left"],
)
def test_each_move_goes_one_cell_in_its_direction(name, expected):
    rules = CompassRules()
    board = Board.parse("#####\n#...#\n#.A.#\n#...#\n#####")
    after = rules.apply(board, rules.find_move(board, name))
    assert after.agent == Position(*expected)


def test_a_wall_blocks_the_move():
    rules = CompassRules()
    board = Board.parse("###\n#A#\n###")
    assert rules.apply(board, rules.find_move(board, "east")) == board


def test_stepping_onto_the_key_picks_it_up():
    rules = CompassRules()
    board = Board.parse("####\n#AK#\n####")
    after = rules.apply(board, rules.find_move(board, "east"))
    assert after.holding == ("key",)
    assert after.at(after.agent) == "."


def test_a_locked_door_blocks_you_without_the_key():
    rules = CompassRules()
    board = Board.parse("####\n#AD#\n####")
    assert rules.apply(board, rules.find_move(board, "east")) == board


def test_the_key_opens_the_door_and_you_step_through():
    rules = CompassRules()
    board = Board.parse("#####\n#AKD#\n#####")
    for _ in range(2):
        board = rules.apply(board, rules.find_move(board, "east"))
    assert board.agent == Position(3, 1)
    assert board.at(board.agent) == "."


def test_standing_on_the_goal_wins():
    rules = CompassRules()
    board = Board.parse("####\n#AG#\n####")
    assert not rules.is_won(board)
    assert rules.is_won(rules.apply(board, rules.find_move(board, "east")))


@pytest.mark.parametrize(
    ("before", "name", "expected"),
    [
        ("#####\n#A.G#\n#####", "east", "you move to (2, 1)"),
        ("#####\n#A.G#\n#####", "west", "blocked, you stay at (1, 1)"),
        ("####\n#AK#\n####", "east", "you move to (2, 1) and pick up the key"),
        ("####\n#AG#\n####", "east", "you move to (2, 1) and reach the goal"),
    ],
    ids=["moving", "into a wall", "onto the key", "onto the goal"],
)
def test_an_outcome_is_described_in_plain_words(before, name, expected):
    rules = CompassRules()
    board = Board.parse(before)
    after = rules.apply(board, rules.find_move(board, name))
    assert rules.describe_outcome(board, after) == expected


def test_unlocking_the_door_is_described():
    rules = CompassRules()
    board = Board.parse("####\n#AD#\n####").pick_up("key")
    after = rules.apply(board, rules.find_move(board, "east"))
    assert rules.describe_outcome(board, after) == "you move to (2, 1) and unlock the door"


def test_the_compass_rules_describe_what_is_next_to_you():
    board = Board.parse("#####\n#.D.#\n#KAG#\n#####")
    around = CompassRules().describe_surroundings(board).splitlines()[0]
    assert around == (
        "North of you is the locked door. South of you is a wall. "
        "East of you is the goal. West of you is the key."
    )


def test_the_compass_rules_say_where_things_are_relative_to_you():
    board = Board.parse("######\n#A...#\n#..K.#\n#...G#\n######")
    assert CompassRules().describe_surroundings(board).splitlines()[1] == (
        "The goal is 3 east and 2 south of you. The key is 2 east and 1 south of you."
    )


def test_a_carried_key_is_no_longer_placed_relative_to_you():
    rules = CompassRules()
    board = Board.parse("#####\n#AKG#\n#####")
    after = rules.apply(board, rules.find_move(board, "east"))
    assert rules.describe_surroundings(after).splitlines()[1] == "The goal is 1 east of you."


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("######\n#AKDG#\n######", "the key K at (2, 1)"),
        ("#####\n#ADG#\n#####", "the locked door D at (2, 1)"),
        ("####\n#AG#\n####", "the goal G at (2, 1)"),
    ],
    ids=["the key first", "then the door", "then the goal"],
)
def test_the_next_target_is_the_key_then_the_door_then_the_goal(text, expected):
    assert CompassRules().describe_next_target(Board.parse(text)) == expected


def test_the_rules_are_found_by_name():
    assert isinstance(make_rules("compass"), CompassRules)
    with pytest.raises(ValueError, match="unknown rules"):
        make_rules("chess")


def test_a_sequence_move_is_every_ordering_of_compass_moves():
    board = Board.parse("###\n#A#\n###")
    two = TwoMoveRules()
    assert len(two.moves(board)) == 16
    assert len(ThreeMoveRules().moves(board)) == 64
    assert two.find_move(board, "north,north") is not None
    assert two.find_move(board, "east,north").description == "move east (right), then north (up)"


@pytest.mark.parametrize(
    ("rules", "text", "name", "expected"),
    [
        (TwoMoveRules(), "#####\n#...#\n#A..#\n#####", "north,east", (2, 1)),
        (ThreeMoveRules(), "######\n#A...#\n######", "east,east,west", (2, 1)),
    ],
    ids=["a two-step move in order", "a three-step move in order"],
)
def test_a_sequence_takes_its_steps_in_order(rules, text, name, expected):
    board = Board.parse(text)
    assert rules.apply(board, rules.find_move(board, name)).agent == Position(*expected)


def test_a_blocked_step_is_wasted_and_the_rest_are_still_taken():
    two = TwoMoveRules()
    board = Board.parse("#####\n#A..#\n#####")
    assert two.apply(board, two.find_move(board, "north,east")).agent == Position(2, 1)


def test_reaching_the_goal_ends_the_sequence_there():
    three = ThreeMoveRules()
    board = Board.parse("######\n#AG..#\n######")
    after = three.apply(board, three.find_move(board, "east,east,east"))
    assert after.agent == Position(2, 1)
    assert three.is_won(after)


def test_a_sequence_can_pick_up_the_key_and_open_the_door():
    two = TwoMoveRules()
    board = Board.parse("#####\n#AKD#\n#####")
    after = two.apply(board, two.find_move(board, "east,east"))
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
    ids=["moving on", "back to where it started", "into a wall", "onto the key", "onto the goal"],
)
def test_a_sequence_is_described_by_where_it_ends_and_what_happened(before, name, expected):
    two = TwoMoveRules()
    board = Board.parse(before)
    after = two.apply(board, two.find_move(board, name))
    assert two.describe_outcome(board, after) == expected


@pytest.mark.parametrize(
    ("rules", "level", "expected"),
    [
        (CompassRules(), 1, 1),
        (CompassRules(), 4, 4),
        (CompassRules(), 10, 10),
        (TwoMoveRules(), 1, 1),
        (TwoMoveRules(), 4, 2),
        (TwoMoveRules(), 10, 5),
        (ThreeMoveRules(), 1, 1),
        (ThreeMoveRules(), 4, 2),
        (ThreeMoveRules(), 10, 4),
    ],
    ids=[
        "one step is one move",
        "four steps are four compass moves",
        "ten steps are ten compass moves",
        "one step is one two-step move",
        "four steps are two two-step moves",
        "ten steps are five two-step moves",
        "one step is one three-step move",
        "four steps are two three-step moves",
        "ten steps are four three-step moves, the last cut short",
    ],
)
def test_a_level_takes_its_distance_over_the_sequence_length_rounded_up(rules, level, expected):
    assert rules.moves_for(level) == expected


def test_sequence_rules_count_levels_in_compass_moves():
    assert isinstance(TwoMoveRules().step_rules(), CompassRules)


def test_the_compass_rules_count_levels_in_their_own_moves():
    rules = CompassRules()
    assert rules.step_rules() is rules


def test_the_sequence_rules_are_found_by_name():
    assert isinstance(make_rules("two-moves"), TwoMoveRules)
    assert isinstance(make_rules("three-moves"), ThreeMoveRules)


def test_the_up_to_rules_offer_every_shorter_sequence_too():
    board = Board.parse("###\n#A#\n###")
    three = UpToThreeMoveRules()
    assert len(UpToTwoMoveRules().moves(board)) == 4 + 16
    assert len(three.moves(board)) == 4 + 16 + 64
    assert three.find_move(board, "east").description == "move east (right)"
    assert three.find_move(board, "east,north") is not None
    assert three.find_move(board, "east,north,west") is not None


def test_under_the_up_to_rules_a_single_step_goes_one_cell():
    three = UpToThreeMoveRules()
    board = Board.parse("######\n#A...#\n######")
    assert three.apply(board, three.find_move(board, "east")).agent == Position(2, 1)


@pytest.mark.parametrize(
    ("rules", "level", "expected"),
    [
        (UpToTwoMoveRules(), 1, 1),
        (UpToTwoMoveRules(), 4, 2),
        (UpToTwoMoveRules(), 10, 5),
        (UpToThreeMoveRules(), 1, 1),
        (UpToThreeMoveRules(), 4, 2),
        (UpToThreeMoveRules(), 10, 4),
    ],
    ids=[
        "one step is one up-to-two move",
        "four steps are two up-to-two moves",
        "ten steps are five up-to-two moves",
        "one step is one up-to-three move",
        "four steps are two up-to-three moves",
        "ten steps are four up-to-three moves",
    ],
)
def test_a_shorter_move_never_wins_in_fewer_moves(rules, level, expected):
    assert rules.moves_for(level) == expected


def test_the_up_to_rules_say_a_move_may_be_shorter_and_are_found_by_name():
    assert "a path of one, two or three steps" in UpToThreeMoveRules().description
    assert "a path of one or two steps" in UpToTwoMoveRules().description
    assert isinstance(make_rules("up-to-two-moves"), UpToTwoMoveRules)
    assert isinstance(make_rules("up-to-three-moves"), UpToThreeMoveRules)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("#####\n#A.G#\n#####", 2),
        ("#####\n#KDG#\n#A###\n#####", 3),
        ("#####\n#A#G#\n#####", None),
    ],
    ids=["a straight line", "fetching the key first", "a goal behind a wall"],
)
def test_the_distance_to_the_goal(text, expected):
    assert Solver(CompassRules()).fewest_moves(Board.parse(text)) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("#####\n#A..#\n#.G.#\n#####", ("south", "east")),
        ("#####\n#A#.#\n#.G.#\n#####", ("south",)),
        ("#####\n#A#G#\n#####", ()),
    ],
    ids=[
        "ties are kept",
        "walking into a wall is never best",
        "a goal that cannot be reached has none",
    ],
)
def test_the_moves_that_start_a_shortest_path(text, expected):
    assert Solver(CompassRules()).best_moves(Board.parse(text)) == expected


def test_there_are_no_best_moves_once_the_goal_is_reached():
    rules = CompassRules()
    start = Board.parse("####\n#AG#\n####")
    board = rules.apply(start, rules.find_move(start, "east"))
    assert Solver(rules).best_moves(board) == ()


def test_best_moves_can_reuse_the_distances_from_an_earlier_board():
    rules = CompassRules()
    start = Board.parse("#####\n#A..#\n#.G.#\n#####")
    later = rules.apply(start, rules.find_move(start, "east"))
    solver = Solver(rules)
    assert solver.best_moves(later, solver.distances(start)) == solver.best_moves(later)


@pytest.mark.parametrize("rules", [CompassRules(), ThreeMoveRules()], ids=["compass", "three-step"])
@pytest.mark.parametrize("name", ["gen-03-01", "gen-08-01", "maze", "gen-20-01"])
def test_the_distances_from_a_board_agree_with_a_search_from_each_board(rules, name):
    board = load_puzzles()[name].board
    solver = Solver(rules)
    distances = solver.distances(board)
    assert distances[board] == solver.fewest_moves(board)
    for move in rules.moves(board):
        after = rules.apply(board, move)
        assert distances.get(after) == solver.fewest_moves(after)

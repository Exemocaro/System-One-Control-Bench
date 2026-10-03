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

COMPASS = CompassRules()
TWO = TwoMoveRules()
THREE = ThreeMoveRules()
UP_TO_TWO = UpToTwoMoveRules()
UP_TO_THREE = UpToThreeMoveRules()
OPEN = "#####\n#...#\n#.A.#\n#...#\n#####"


def move(rules, text, name):
    board = Board.parse(text)
    return board, rules.apply(board, rules.find_move(board, name))


def test_parsing_finds_the_agent_and_leaves_floor_under_it():
    board = Board.parse("#####\n#AG.#\n#####")
    assert (board.agent, board.at(board.agent)) == (Position(1, 1), ".")


def test_parsing_draws_the_agent_back_on_the_map():
    assert Board.parse("#####\n#AG.#\n#####").draw() == "#####\n#AG.#\n#####"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("#####\n#.G.#\n#####", "exactly one A"),
        ("#####\n#AX.#\n#####", "unknown"),
        ("#####\n#AG#\n#####", "same width"),
    ],
    ids=["no agent", "unknown symbol", "different widths"],
)
def test_a_map_that_cannot_be_read_is_refused(text, message):
    with pytest.raises(ValueError, match=message):
        Board.parse(text)


@pytest.mark.parametrize(
    ("position", "expected"),
    [(Position(-1, 0), "#"), (Position(9, 9), "#"), (Position(2, 1), "G")],
    ids=["left of the map", "below the map", "inside the map"],
)
def test_a_cell_outside_the_map_counts_as_wall(position, expected):
    assert Board.parse("#####\n#AG.#\n#####").at(position) == expected


def test_find_lists_every_cell_with_a_symbol():
    assert Board.parse("#####\n#AG.#\n#####").find("G") == (Position(2, 1),)


def test_the_compass_rules_always_offer_the_same_four_moves():
    moves = COMPASS.moves(Board.parse("###\n#A#\n###"))
    assert [m.name for m in moves] == ["north", "south", "east", "west"]


@pytest.mark.parametrize(
    ("rules", "count"),
    [(COMPASS, 4), (TWO, 16), (THREE, 64), (UP_TO_TWO, 4 + 16), (UP_TO_THREE, 4 + 16 + 64)],
    ids=["compass", "two-moves", "three-moves", "up-to-two", "up-to-three"],
)
def test_the_rules_offer_every_sequence_up_to_their_length(rules, count):
    assert len(rules.moves(Board.parse("###\n#A#\n###"))) == count


@pytest.mark.parametrize(
    ("rules", "name"),
    [(TWO, "north,north"), (UP_TO_THREE, "east"), (UP_TO_THREE, "east,north,west")],
    ids=["a two-step move", "a single step under up-to", "a three-step move under up-to"],
)
def test_a_sequence_is_found_by_its_name(rules, name):
    assert rules.find_move(Board.parse("###\n#A#\n###"), name) is not None


@pytest.mark.parametrize(
    ("rules", "name", "expected"),
    [
        (TWO, "east,north", "move east (right), then north (up)"),
        (UP_TO_THREE, "east", "move east (right)"),
    ],
    ids=["a sequence", "a single step"],
)
def test_a_move_describes_itself(rules, name, expected):
    assert rules.find_move(Board.parse("###\n#A#\n###"), name).description == expected


# Each row: the rules, the board before, the move, then where the agent is, what it carries and
# whether it won.
@pytest.mark.parametrize(
    ("rules", "text", "name", "agent", "holding", "won"),
    [
        (COMPASS, OPEN, "north", (2, 1), (), False),
        (COMPASS, OPEN, "south", (2, 3), (), False),
        (COMPASS, OPEN, "east", (3, 2), (), False),
        (COMPASS, OPEN, "west", (1, 2), (), False),
        (COMPASS, "###\n#A#\n###", "east", (1, 1), (), False),
        (COMPASS, "####\n#AK#\n####", "east", (2, 1), ("key",), False),
        (COMPASS, "####\n#AD#\n####", "east", (1, 1), (), False),
        (COMPASS, "####\n#AG#\n####", "east", (2, 1), (), True),
        (TWO, "#####\n#...#\n#A..#\n#####", "north,east", (2, 1), (), False),
        (THREE, "######\n#A...#\n######", "east,east,west", (2, 1), (), False),
        (TWO, "#####\n#A..#\n#####", "north,east", (2, 1), (), False),
        (THREE, "######\n#AG..#\n######", "east,east,east", (2, 1), (), True),
        (TWO, "#####\n#AKD#\n#####", "east,east", (3, 1), ("key",), False),
        (UP_TO_THREE, "######\n#A...#\n######", "east", (2, 1), (), False),
    ],
    ids=[
        "north goes one cell up",
        "south goes down",
        "east goes right",
        "west goes left",
        "a wall blocks the move",
        "the key is picked up",
        "a locked door blocks without the key",
        "the goal wins",
        "two steps in order",
        "three steps in order",
        "a blocked step is wasted, the rest are taken",
        "reaching the goal ends the sequence there",
        "a sequence takes the key and opens the door",
        "a single step under the up-to rules",
    ],
)
def test_a_move_changes_the_board(rules, text, name, agent, holding, won):
    _, after = move(rules, text, name)
    assert (after.agent, after.holding, rules.is_won(after)) == (Position(*agent), holding, won)


def test_a_key_picked_up_leaves_floor_behind():
    _, after = move(COMPASS, "####\n#AK#\n####", "east")
    assert after.at(after.agent) == "."


@pytest.mark.parametrize(
    ("rules", "text", "name", "expected"),
    [
        (COMPASS, "#####\n#A.G#\n#####", "east", "you move to (2, 1)"),
        (COMPASS, "#####\n#A.G#\n#####", "west", "blocked, you stay at (1, 1)"),
        (COMPASS, "####\n#AK#\n####", "east", "you move to (2, 1) and pick up the key"),
        (COMPASS, "####\n#AG#\n####", "east", "you move to (2, 1) and reach the goal"),
        (TWO, "#####\n#A..#\n#####", "east,east", "you end at (3, 1)"),
        (TWO, "#####\n#A..#\n#####", "east,west", "you end where you started, at (1, 1)"),
        (TWO, "#####\n#A..#\n#####", "north,west", "you end where you started, at (1, 1)"),
        (TWO, "#####\n#AK.#\n#####", "east,east", "you end at (3, 1) and pick up the key"),
        (TWO, "#####\n#AG.#\n#####", "east,east", "you end at (2, 1) and reach the goal"),
    ],
    ids=[
        "moving",
        "into a wall",
        "onto the key",
        "onto the goal",
        "a sequence moving on",
        "a sequence back where it started",
        "a sequence into a wall",
        "a sequence onto the key",
        "a sequence onto the goal",
    ],
)
def test_an_outcome_is_described_in_plain_words(rules, text, name, expected):
    before, after = move(rules, text, name)
    assert rules.describe_outcome(before, after) == expected


def test_unlocking_the_door_is_described():
    board = Board.parse("####\n#AD#\n####").pick_up("key")
    after = COMPASS.apply(board, COMPASS.find_move(board, "east"))
    assert COMPASS.describe_outcome(board, after) == "you move to (2, 1) and unlock the door"


@pytest.mark.parametrize(
    ("text", "line", "expected"),
    [
        (
            "#####\n#.D.#\n#KAG#\n#####",
            0,
            "North of you is the locked door. South of you is a wall. "
            "East of you is the goal. West of you is the key.",
        ),
        (
            "######\n#A...#\n#..K.#\n#...G#\n######",
            1,
            "The goal is 3 east and 2 south of you. The key is 2 east and 1 south of you.",
        ),
    ],
    ids=["what is next to you", "where things are relative to you"],
)
def test_the_compass_rules_describe_the_surroundings(text, line, expected):
    assert COMPASS.describe_surroundings(Board.parse(text)).splitlines()[line] == expected


def test_a_carried_key_is_no_longer_placed_relative_to_you():
    _, after = move(COMPASS, "#####\n#AKG#\n#####", "east")
    assert COMPASS.describe_surroundings(after).splitlines()[1] == "The goal is 1 east of you."


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
    assert COMPASS.describe_next_target(Board.parse(text)) == expected


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("compass", CompassRules),
        ("two-moves", TwoMoveRules),
        ("three-moves", ThreeMoveRules),
        ("up-to-two-moves", UpToTwoMoveRules),
        ("up-to-three-moves", UpToThreeMoveRules),
    ],
)
def test_the_rules_are_found_by_name(name, kind):
    assert isinstance(make_rules(name), kind)


def test_unknown_rules_are_refused():
    with pytest.raises(ValueError, match="unknown rules"):
        make_rules("chess")


@pytest.mark.parametrize(
    ("rules", "level", "expected"),
    [
        (COMPASS, 1, 1),
        (COMPASS, 4, 4),
        (COMPASS, 10, 10),
        (TWO, 1, 1),
        (TWO, 4, 2),
        (TWO, 10, 5),
        (THREE, 1, 1),
        (THREE, 4, 2),
        (THREE, 10, 4),
        (UP_TO_TWO, 1, 1),
        (UP_TO_TWO, 4, 2),
        (UP_TO_TWO, 10, 5),
        (UP_TO_THREE, 1, 1),
        (UP_TO_THREE, 4, 2),
        (UP_TO_THREE, 10, 4),
    ],
    ids=[
        "compass, 1 step",
        "compass, 4 steps",
        "compass, 10 steps",
        "two-moves, 1 step",
        "two-moves, 4 steps",
        "two-moves, 10 steps",
        "three-moves, 1 step",
        "three-moves, 4 steps",
        "three-moves, 10 steps, the last cut short",
        "up-to-two, 1 step",
        "up-to-two, 4 steps",
        "up-to-two, 10 steps",
        "up-to-three, 1 step",
        "up-to-three, 4 steps",
        "up-to-three, 10 steps",
    ],
)
def test_a_level_takes_its_distance_over_the_sequence_length_rounded_up(rules, level, expected):
    assert rules.moves_for(level) == expected


def test_sequence_rules_count_levels_in_compass_moves():
    assert isinstance(TWO.step_rules(), CompassRules)


def test_the_compass_rules_count_levels_in_their_own_moves():
    assert COMPASS.step_rules() is COMPASS


@pytest.mark.parametrize(
    ("rules", "fragment"),
    [
        (UP_TO_THREE, "a path of one, two or three steps"),
        (UP_TO_TWO, "a path of one or two steps"),
    ],
    ids=["up-to-three", "up-to-two"],
)
def test_the_up_to_rules_say_a_move_may_be_shorter(rules, fragment):
    assert fragment in rules.description


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
    assert Solver(COMPASS).fewest_moves(Board.parse(text)) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("#####\n#A..#\n#.G.#\n#####", ("south", "east")),
        ("#####\n#A#.#\n#.G.#\n#####", ("south",)),
        ("#####\n#A#G#\n#####", ()),
    ],
    ids=["ties are kept", "a wall is never best", "an unreachable goal has none"],
)
def test_the_moves_that_start_a_shortest_path(text, expected):
    assert Solver(COMPASS).best_moves(Board.parse(text)) == expected


def test_there_are_no_best_moves_once_the_goal_is_reached():
    _, after = move(COMPASS, "####\n#AG#\n####", "east")
    assert Solver(COMPASS).best_moves(after) == ()


def test_best_moves_can_reuse_the_distances_from_an_earlier_board():
    start, later = move(COMPASS, "#####\n#A..#\n#.G.#\n#####", "east")
    solver = Solver(COMPASS)
    assert solver.best_moves(later, solver.distances(start)) == solver.best_moves(later)


@pytest.mark.parametrize("rules", [COMPASS, THREE], ids=["compass", "three-moves"])
@pytest.mark.parametrize("name", ["gen-03-01", "gen-08-01", "maze", "gen-20-01"])
def test_the_distances_from_a_board_agree_with_a_search_from_each_board(rules, name):
    board = load_puzzles()[name].board
    solver = Solver(rules)
    distances = solver.distances(board)
    assert distances[board] == solver.fewest_moves(board)
    assert all(
        distances.get(rules.apply(board, m)) == solver.fewest_moves(rules.apply(board, m))
        for m in rules.moves(board)
    )

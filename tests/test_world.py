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
LINE = "#####\n#A..#\n#####"


def move(rules, text, name):
    board = Board.parse(text)
    return board, rules.apply(board, rules.find_move(board, name))


def test_parsing_finds_the_agent_and_leaves_floor_under_it():
    board = Board.parse("#####\n#AG.#\n#####")
    assert (board.agent, board.at(board.agent), board.find("G")) == (
        Position(1, 1),
        ".",
        (Position(2, 1),),
    )


def test_parsing_draws_the_agent_back_on_the_map():
    assert Board.parse("#####\n#AG.#\n#####").draw() == "#####\n#AG.#\n#####"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        pytest.param("#####\n#.G.#\n#####", "exactly one A", id="no agent"),
        pytest.param("#####\n#AX.#\n#####", "unknown", id="unknown symbol"),
        pytest.param("#####\n#AG#\n#####", "same width", id="different widths"),
    ],
)
def test_a_map_that_cannot_be_read_is_refused(text, message):
    with pytest.raises(ValueError, match=message):
        Board.parse(text)


def test_a_cell_outside_the_map_counts_as_wall():
    assert Board.parse(LINE).at(Position(-1, 0)) == "#"


@pytest.mark.parametrize(
    ("rules", "count"),
    [
        pytest.param(COMPASS, 4, id="compass"),
        pytest.param(TWO, 16, id="two-moves"),
        pytest.param(THREE, 64, id="three-moves"),
        pytest.param(UP_TO_TWO, 4 + 16, id="up-to-two"),
        pytest.param(UP_TO_THREE, 4 + 16 + 64, id="up-to-three"),
    ],
)
def test_the_rules_offer_every_sequence_up_to_their_length(rules, count):
    assert len(rules.moves(Board.parse("###\n#A#\n###"))) == count


@pytest.mark.parametrize(
    ("rules", "name", "expected"),
    [
        pytest.param(COMPASS, "north", "north", id="a compass move"),
        pytest.param(TWO, "east,north", "move east (right), then north (up)", id="a sequence"),
        pytest.param(UP_TO_THREE, "east", "move east (right)", id="a single step under up-to"),
    ],
)
def test_a_move_is_found_by_name_and_describes_itself(rules, name, expected):
    found = rules.find_move(Board.parse("###\n#A#\n###"), name)
    assert expected in (found.name, found.description)


# Each row: rules, board, move, then where the agent ends up, what it carries, whether it won.
@pytest.mark.parametrize(
    ("rules", "text", "name", "agent", "holding", "won"),
    [
        pytest.param(COMPASS, OPEN, "north", (2, 1), (), False, id="north goes one cell up"),
        pytest.param(COMPASS, OPEN, "east", (3, 2), (), False, id="east goes right"),
        pytest.param(COMPASS, LINE, "north", (1, 1), (), False, id="a wall blocks the move"),
        pytest.param(COMPASS, "####\n#AK#\n####", "east", (2, 1), ("key",), False, id="the key"),
        pytest.param(COMPASS, "####\n#AD#\n####", "east", (1, 1), (), False, id="a locked door"),
        pytest.param(COMPASS, "####\n#AG#\n####", "east", (2, 1), (), True, id="the goal wins"),
        pytest.param(TWO, OPEN, "north,east", (3, 1), (), False, id="two steps in order"),
        pytest.param(TWO, LINE, "north,east", (2, 1), (), False, id="a blocked step is wasted"),
        pytest.param(
            THREE,
            "######\n#AG..#\n######",
            "east,east,east",
            (2, 1),
            (),
            True,
            id="the goal ends a sequence",
        ),
        pytest.param(
            TWO,
            "#####\n#AKD#\n#####",
            "east,east",
            (3, 1),
            ("key",),
            False,
            id="key and door in one move",
        ),
        pytest.param(UP_TO_THREE, LINE, "east", (2, 1), (), False, id="a single step under up-to"),
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
        pytest.param(COMPASS, LINE, "east", "you move to (2, 1)", id="moving"),
        pytest.param(COMPASS, LINE, "north", "blocked, you stay at (1, 1)", id="into a wall"),
        pytest.param(
            COMPASS,
            "####\n#AK#\n####",
            "east",
            "you move to (2, 1) and pick up the key",
            id="onto the key",
        ),
        pytest.param(
            COMPASS,
            "####\n#AG#\n####",
            "east",
            "you move to (2, 1) and reach the goal",
            id="onto the goal",
        ),
        pytest.param(TWO, LINE, "east,east", "you end at (3, 1)", id="a sequence moving on"),
        pytest.param(
            TWO,
            LINE,
            "east,west",
            "you end where you started, at (1, 1)",
            id="a sequence back again",
        ),
        pytest.param(
            TWO,
            "#####\n#AG.#\n#####",
            "east,east",
            "you end at (2, 1) and reach the goal",
            id="a sequence onto the goal",
        ),
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
        pytest.param(
            "#####\n#.D.#\n#KAG#\n#####",
            0,
            "North of you is the locked door. South of you is a wall. "
            "East of you is the goal. West of you is the key.",
            id="what is next to you",
        ),
        pytest.param(
            "######\n#A...#\n#..K.#\n#...G#\n######",
            1,
            "The goal is 3 east and 2 south of you. The key is 2 east and 1 south of you.",
            id="where things are relative to you",
        ),
    ],
)
def test_the_compass_rules_describe_the_surroundings(text, line, expected):
    assert COMPASS.describe_surroundings(Board.parse(text)).splitlines()[line] == expected


def test_a_carried_key_is_no_longer_placed_relative_to_you():
    _, after = move(COMPASS, "#####\n#AKG#\n#####", "east")
    assert COMPASS.describe_surroundings(after).splitlines()[1] == "The goal is 1 east of you."


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("######\n#AKDG#\n######", "the key K at (2, 1)", id="the key first"),
        pytest.param("#####\n#ADG#\n#####", "the locked door D at (2, 1)", id="then the door"),
        pytest.param("####\n#AG#\n####", "the goal G at (2, 1)", id="then the goal"),
    ],
)
def test_the_next_target_is_the_key_then_the_door_then_the_goal(text, expected):
    assert COMPASS.describe_next_target(Board.parse(text)) == expected


def test_unknown_rules_are_refused():
    with pytest.raises(ValueError, match="unknown rules"):
        make_rules("chess")


@pytest.mark.parametrize(
    ("rules", "level", "expected"),
    [
        pytest.param(COMPASS, 10, 10, id="compass counts every step"),
        pytest.param(TWO, 1, 1, id="one step is one move"),
        pytest.param(TWO, 4, 2, id="four steps are two two-step moves"),
        pytest.param(TWO, 10, 5, id="ten steps are five"),
        pytest.param(THREE, 10, 4, id="ten steps are four three-step moves, the last cut short"),
        pytest.param(UP_TO_TWO, 4, 2, id="up-to-two counts as two-moves"),
        pytest.param(UP_TO_THREE, 10, 4, id="up-to-three counts as three-moves"),
    ],
)
def test_a_level_takes_its_distance_over_the_sequence_length_rounded_up(rules, level, expected):
    assert rules.moves_for(level) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("#####\n#A.G#\n#####", 2, id="a straight line"),
        pytest.param("#####\n#KDG#\n#A###\n#####", 3, id="fetching the key first"),
        pytest.param("#####\n#A#G#\n#####", None, id="a goal behind a wall"),
    ],
)
def test_the_distance_to_the_goal(text, expected):
    assert Solver(COMPASS).fewest_moves(Board.parse(text)) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("#####\n#A..#\n#.G.#\n#####", ("south", "east"), id="ties are kept"),
        pytest.param("#####\n#A#.#\n#.G.#\n#####", ("south",), id="a wall is never best"),
        pytest.param("#####\n#A#G#\n#####", (), id="an unreachable goal has none"),
    ],
)
def test_the_moves_that_start_a_shortest_path(text, expected):
    assert Solver(COMPASS).best_moves(Board.parse(text)) == expected


def test_best_moves_can_reuse_the_distances_from_an_earlier_board():
    start, later = move(COMPASS, "#####\n#A..#\n#.G.#\n#####", "east")
    solver = Solver(COMPASS)
    assert solver.best_moves(later, solver.distances(start)) == solver.best_moves(later)


@pytest.mark.parametrize("rules", [COMPASS, THREE], ids=["compass", "three-moves"])
@pytest.mark.parametrize("name", ["gen-03-01", "maze"])
def test_the_distances_from_a_board_agree_with_a_search_from_each_board(rules, name):
    board = load_puzzles()[name].board
    solver = Solver(rules)
    distances = solver.distances(board)
    assert distances[board] == solver.fewest_moves(board)
    assert all(
        distances.get(rules.apply(board, m)) == solver.fewest_moves(rules.apply(board, m))
        for m in rules.moves(board)
    )

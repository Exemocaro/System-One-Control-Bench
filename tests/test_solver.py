import pytest

from system_one_control.board import Board
from system_one_control.rules import CompassRules, ThreeMoveRules
from system_one_control.scenario import load_scenarios
from system_one_control.solver import Solver

solver = Solver(CompassRules())


def test_distance_along_a_straight_line():
    assert solver.moves_to_goal(Board.parse("#####\n#A.G#\n#####")) == 2


def test_distance_includes_fetching_the_key():
    assert solver.moves_to_goal(Board.parse("#####\n#KDG#\n#A###\n#####")) == 3


def test_an_unreachable_goal_has_no_distance():
    assert solver.moves_to_goal(Board.parse("#####\n#A#G#\n#####")) is None


def test_best_moves_keep_ties():
    assert solver.best_moves(Board.parse("#####\n#A..#\n#.G.#\n#####")) == ("south", "east")


def test_best_moves_never_include_walking_into_a_wall():
    assert solver.best_moves(Board.parse("#####\n#A#.#\n#.G.#\n#####")) == ("south",)


def test_there_are_no_best_moves_once_the_goal_is_reached():
    start = Board.parse("####\n#AG#\n####")
    board = solver.rules.apply(start, solver.rules.find_move(start, "east"))
    assert solver.best_moves(board) == ()


def test_there_are_no_best_moves_where_the_goal_cannot_be_reached():
    assert solver.best_moves(Board.parse("#####\n#A#G#\n#####")) == ()


@pytest.mark.parametrize("rules", [CompassRules(), ThreeMoveRules()], ids=lambda r: r.name)
@pytest.mark.parametrize("name", ["gen-03-01", "gen-08-01", "maze", "gen-20-01"])
def test_the_distances_from_a_board_agree_with_a_search_from_each_board(rules, name):
    board = load_scenarios()[name].board
    distances = Solver(rules).distances(board)
    assert distances[board] == Solver(rules).moves_to_goal(board)
    for after in {rules.apply(board, move) for move in rules.moves(board)}:
        assert distances.get(after) == Solver(rules).moves_to_goal(after)


def test_best_moves_can_reuse_the_distances_from_an_earlier_board():
    start = Board.parse("#####\n#A..#\n#.G.#\n#####")
    later = CompassRules().apply(start, CompassRules.MOVES[2])  # east
    assert solver.best_moves(later, solver.distances(start)) == solver.best_moves(later)

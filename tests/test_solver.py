from system_one_control.board import Board
from system_one_control.rules import CompassRules
from system_one_control.solver import Solver

solver = Solver(CompassRules())


def test_distance_along_a_straight_line():
    assert solver.distance(Board.parse("#####\n#A.G#\n#####")) == 2


def test_distance_includes_fetching_the_key():
    assert solver.distance(Board.parse("#####\n#KDG#\n#A###\n#####")) == 3


def test_an_unreachable_goal_has_no_distance():
    assert solver.distance(Board.parse("#####\n#A#G#\n#####")) is None


def test_best_moves_keep_ties():
    assert solver.best_moves(Board.parse("#####\n#A..#\n#.G.#\n#####")) == ("south", "east")


def test_best_moves_never_include_walking_into_a_wall():
    assert solver.best_moves(Board.parse("#####\n#A#.#\n#.G.#\n#####")) == ("south",)


def test_there_are_no_best_moves_once_the_goal_is_reached():
    start = Board.parse("####\n#AG#\n####")
    board = solver.rules.apply(start, solver.rules.find_move(start, "east"))
    assert solver.best_moves(board) == ()

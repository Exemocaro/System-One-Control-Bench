import pytest

from system_one_control.board import Board, Position

MAP = """
#####
#AG.#
#####
"""


def test_parse_finds_the_agent_and_leaves_floor_under_it():
    board = Board.parse(MAP)
    assert board.agent == Position(1, 1)
    assert board.at(Position(1, 1)) == "."


def test_draw_puts_the_agent_back_on_the_map():
    assert Board.parse(MAP).draw() == "#####\n#AG.#\n#####"


def test_a_map_needs_exactly_one_agent():
    with pytest.raises(ValueError, match="exactly one A"):
        Board.parse("#####\n#.G.#\n#####")


def test_unknown_symbols_are_rejected():
    with pytest.raises(ValueError, match="unknown"):
        Board.parse("#####\n#AX.#\n#####")


def test_rows_must_have_the_same_width():
    with pytest.raises(ValueError, match="same width"):
        Board.parse("#####\n#AG#\n#####")


def test_outside_the_map_counts_as_wall():
    assert Board.parse(MAP).at(Position(-1, 0)) == "#"


def test_find_lists_every_cell_with_a_symbol():
    assert Board.parse(MAP).find("G") == (Position(2, 1),)

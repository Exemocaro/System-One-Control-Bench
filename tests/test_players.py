import pytest

from system_one_control.players import PLAYERS, Turn, make_player
from system_one_control.players.baselines import (
    GreedyPlayer,
    RandomPlayer,
    SolverPlayer,
    WallAwareGreedyPlayer,
)
from system_one_control.players.remote import LLM_MODELS
from system_one_control.world import Board, CompassRules
from tests.helpers import MAP, turn

rules = CompassRules()


def test_random_picks_an_offered_move_and_is_reproducible():
    t = turn("#####\n#A.G#\n#####")
    assert RandomPlayer(seed=1).choose(t).move in rules.STEPS
    assert RandomPlayer(seed=1).choose(t).move == RandomPlayer(seed=1).choose(t).move


@pytest.mark.parametrize(
    ("player", "board", "expected"),
    [
        (SolverPlayer(), "#####\n#A#.#\n#.G.#\n#####", "south"),
        (GreedyPlayer(), "#######\n#K.A.G#\n#######", "west"),
        (GreedyPlayer(), "#######\n#..A.G#\n#######", "east"),
        (GreedyPlayer(), "#####\n#A#G#\n#...#\n#####", "east"),
        (WallAwareGreedyPlayer(), "#####\n#A#G#\n#...#\n#####", "south"),
    ],
    ids=[
        "the solver picks a best move",
        "greedy heads for the key before the goal",
        "greedy heads straight for the goal",
        "greedy walks into the wall between it and the goal",
        "greedy with walls steps around instead",
    ],
)
def test_a_baseline_picks_its_move(player, board, expected):
    assert player.choose(turn(board)).move == expected


def test_greedy_breaks_ties_the_same_way_whatever_the_option_order():
    board = Board.parse("####\n#A.#\n#.G#\n####")
    requests = [MAP.render(board, rules, shuffle_seed=seed) for seed in "abcd"]
    moves = {GreedyPlayer().choose(Turn(board, rules, request)).move for request in requests}
    assert moves == {"south"}  # south and east both close in; south comes first in the rules


def test_players_are_built_by_name():
    assert isinstance(make_player("random"), RandomPlayer)
    with pytest.raises(ValueError, match="unknown player"):
        make_player("chess-engine")


def test_only_jev_and_the_chat_models_cost_money():
    paid = {name for name, entry in PLAYERS.items() if entry.paid}
    assert paid == {"jev", *LLM_MODELS, *(f"{name}-think" for name in LLM_MODELS)}

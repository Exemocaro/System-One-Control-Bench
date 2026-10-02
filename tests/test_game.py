import threading
from dataclasses import replace

import pytest

from system_one_control.game import Game
from system_one_control.players import Choice, Player, Turn
from system_one_control.players.baselines import SolverPlayer
from system_one_control.prompts import CONDITIONS
from system_one_control.puzzles import load_scenarios
from system_one_control.world import ThreeMoveRules, TwoMoveRules
from tests.helpers import MAP, AlwaysPlayer, scenario

SCENARIOS = load_scenarios()


@pytest.mark.parametrize("name", SCENARIOS)
def test_the_solver_wins_every_scenario_in_the_fewest_moves(name):
    game = Game(SCENARIOS[name], SolverPlayer(), MAP)
    steps = game.play()
    assert game.won
    assert len(steps) == SCENARIOS[name].moves_to_goal
    assert all(step.optimal for step in steps)


def test_a_step_records_the_board_before_and_after_and_whether_it_was_best():
    game = Game(scenario("#####\n#A.G#\n#####", 2), AlwaysPlayer("west"), MAP)
    step = game.step()
    assert step.number == 1
    assert step.before == step.after
    assert step.best_moves == ("east",)
    assert not step.optimal
    assert "#A.G#" in step.request.state


def test_a_game_stops_after_twice_the_fewest_moves():
    short = scenario("#####\n#A.G#\n#####", 2)
    game = Game(short, AlwaysPlayer("west"), MAP)
    assert len(game.play()) == 4
    assert game.is_over and not game.won


def test_an_answer_that_is_not_an_allowed_move_ends_the_game():
    game = Game(scenario("####\n#AG#\n####", 1), AlwaysPlayer("jump"), MAP)
    step = game.step()
    assert game.is_over and not game.won
    assert step.choice.move is None
    assert "jump" in step.choice.error


def test_no_move_can_be_played_after_the_game_is_over():
    game = Game(scenario("####\n#AG#\n####", 1), SolverPlayer(), MAP)
    game.play()
    with pytest.raises(RuntimeError, match="over"):
        game.step()


def test_the_next_request_shows_the_current_board():
    game = Game(scenario("#####\n#A.G#\n#####", 2), SolverPlayer(), MAP)
    game.step()
    assert "#.AG#" in game.next_request().state


def test_the_previewed_request_is_exactly_what_the_player_is_then_asked():
    game = Game(scenario("#####\n#A.G#\n#####", 2), SolverPlayer(), MAP)
    preview = game.next_request()
    assert game.step().request == preview


def test_each_move_is_asked_with_its_own_option_order():
    game = Game(scenario("########\n#A....G#\n########", 5), SolverPlayer(), MAP)
    orders = {tuple(o.move for o in step.request.options) for step in game.play()}
    assert len(orders) > 1


def test_the_history_lists_every_move_and_what_it_did():
    game = Game(scenario("#####\n#A.G#\n#####", 2), AlwaysPlayer("west"), CONDITIONS["map+memory"])
    game.step()
    game.step()
    assert game.next_request().state.endswith(
        "Moves so far:\n1. west: blocked, you stay at (1, 1)\n2. west: blocked, you stay at (1, 1)"
    )


class FailingPlayer(Player):
    def choose(self, turn: Turn) -> Choice:
        raise ConnectionError("the API is down")


def test_a_player_that_raises_ends_the_game_with_the_error_recorded():
    game = Game(scenario("#####\n#A.G#\n#####", 2), FailingPlayer(), MAP)
    step = game.step()
    assert game.is_over and not game.won
    assert step.choice.move is None
    assert step.choice.error == "ConnectionError: the API is down"


def test_a_game_asked_to_stop_stops_between_moves():
    game = Game(scenario("########\n#A....G#\n########", 5), SolverPlayer(), MAP)
    stop = threading.Event()
    game.step()
    stop.set()
    assert len(game.play(stop)) == 1
    assert not game.is_over


def test_under_sequence_rules_the_solver_wins_in_the_fewest_sequences():
    played = replace(SCENARIOS["gen-10-01"], rules=ThreeMoveRules())
    game = Game(played, SolverPlayer(), MAP)
    steps = game.play()
    assert game.won
    assert len(steps) == played.fewest_moves == 4
    assert all(step.optimal for step in steps)
    assert "," in steps[0].choice.move


def test_under_sequence_rules_the_closest_distance_counts_compass_moves():
    played = replace(scenario("#######\n#A...G#\n#######", 4), rules=TwoMoveRules())
    game = Game(played, AlwaysPlayer("east,north"), MAP)
    game.step()
    assert game.closest == 3  # one compass move nearer, though no sequence was saved
    assert len(game.play()) == played.max_moves == 4


def test_under_sequence_rules_the_closest_distance_takes_in_the_cells_passed_through():
    played = replace(scenario("#######\n#A...G#\n#######", 4), rules=TwoMoveRules())
    game = Game(played, AlwaysPlayer("east,west"), MAP)
    step = game.step()
    assert step.after == step.before
    assert game.closest == 3  # one compass move nearer halfway through the move


@pytest.mark.parametrize("rules", [TwoMoveRules(), ThreeMoveRules()], ids=lambda r: r.name)
def test_the_best_moves_worked_out_once_agree_with_a_fresh_search_at_every_move(rules):
    played = replace(SCENARIOS["gen-10-01"], rules=rules)
    game = Game(played, AlwaysPlayer("east," * (rules.length - 1) + "south"), MAP)
    for step in game.play():
        assert step.best_moves == game.solver.best_moves(step.before)

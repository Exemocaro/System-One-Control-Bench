import pytest

from system_one_control.game import Game
from system_one_control.players import SolverPlayer
from system_one_control.prompt import Prompt
from system_one_control.scenario import load_scenarios
from tests.helpers import PROMPT, AlwaysPlayer, scenario

SCENARIOS = load_scenarios()


@pytest.mark.parametrize("name", SCENARIOS)
def test_the_solver_wins_every_scenario_in_the_fewest_moves(name):
    game = Game(SCENARIOS[name], SolverPlayer(), PROMPT)
    steps = game.play()
    assert game.won
    assert len(steps) == SCENARIOS[name].moves_to_goal
    assert all(step.correct for step in steps)


def test_a_step_records_the_board_before_and_after_and_whether_it_was_best():
    game = Game(scenario("#####\n#A.G#\n#####", 2), AlwaysPlayer("west"), PROMPT)
    step = game.step()
    assert step.number == 1
    assert step.board == step.after
    assert step.best_moves == ("east",)
    assert not step.correct
    assert "#A.G#" in step.request.state


def test_a_game_stops_after_three_times_the_fewest_moves():
    short = scenario("#####\n#A.G#\n#####", 2)
    game = Game(short, AlwaysPlayer("west"), PROMPT)
    assert len(game.play()) == 6
    assert game.over and not game.won


def test_an_answer_that_is_not_an_allowed_move_ends_the_game():
    game = Game(scenario("####\n#AG#\n####", 1), AlwaysPlayer("jump"), PROMPT)
    step = game.step()
    assert game.over and not game.won
    assert step.choice.move is None
    assert "jump" in step.choice.error


def test_no_move_can_be_played_after_the_game_is_over():
    game = Game(scenario("####\n#AG#\n####", 1), SolverPlayer(), PROMPT)
    game.play()
    with pytest.raises(RuntimeError, match="over"):
        game.step()


def test_the_next_request_shows_the_current_board():
    game = Game(scenario("#####\n#A.G#\n#####", 2), SolverPlayer(), PROMPT)
    game.step()
    assert "#.AG#" in game.next_request().state


def test_the_previewed_request_is_exactly_what_the_player_is_then_asked():
    game = Game(scenario("#####\n#A.G#\n#####", 2), SolverPlayer(), PROMPT)
    preview = game.next_request()
    assert game.step().request == preview


def test_each_move_is_asked_with_its_own_option_order():
    game = Game(scenario("########\n#A....G#\n########", 5), SolverPlayer(), PROMPT)
    orders = {tuple(o.move for o in step.request.options) for step in game.play()}
    assert len(orders) > 1


def test_the_history_lists_every_move_and_what_it_did():
    history = Prompt(name="h", description="", state="{history}", question="?")
    game = Game(scenario("#####\n#A.G#\n#####", 2), AlwaysPlayer("west"), history)
    game.step()
    game.step()
    assert game.next_request().state == (
        "Moves so far:\n1. west: blocked, you stay at (1, 1)\n2. west: blocked, you stay at (1, 1)"
    )

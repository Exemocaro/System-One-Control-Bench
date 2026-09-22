import pytest

from system_one_control.game import Game
from system_one_control.players import SolverPlayer
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
    game = Game(scenario("#####\n#A.G#\n#####", 2, ("east",)), AlwaysPlayer("west"), PROMPT)
    step = game.step()
    assert step.number == 1
    assert step.board == step.after
    assert step.best_moves == ("east",)
    assert not step.correct
    assert "#A.G#" in step.request.state


def test_a_game_stops_at_the_move_limit():
    short = scenario("#####\n#A.G#\n#####", 2, ("east",), max_moves=5)
    game = Game(short, AlwaysPlayer("west"), PROMPT)
    assert len(game.play()) == 5
    assert game.over and not game.won


def test_an_answer_that_is_not_an_allowed_move_ends_the_game():
    game = Game(scenario("####\n#AG#\n####", 1, ("east",)), AlwaysPlayer("jump"), PROMPT)
    step = game.step()
    assert game.over and not game.won
    assert step.choice.move is None
    assert "jump" in step.choice.error


def test_no_move_can_be_played_after_the_game_is_over():
    game = Game(scenario("####\n#AG#\n####", 1, ("east",)), SolverPlayer(), PROMPT)
    game.play()
    with pytest.raises(RuntimeError, match="over"):
        game.step()


def test_the_next_request_shows_the_current_board():
    game = Game(scenario("#####\n#A.G#\n#####", 2, ("east",)), SolverPlayer(), PROMPT)
    game.step()
    assert "#.AG#" in game.next_request().state

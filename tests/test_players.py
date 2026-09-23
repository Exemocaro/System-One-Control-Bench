from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from typesafe_sdk import (
    TypeSafeAPITimeoutError,
    TypeSafeBadRequestError,
    TypeSafeError,
    TypeSafeInternalServerError,
)
from typesafe_sdk._core.retry import build_tenacity

from system_one_control.board import Board
from system_one_control.players import (
    JEV_RETRY,
    PLAYERS,
    GreedyPlayer,
    JevPlayer,
    RandomPlayer,
    SolverPlayer,
    Turn,
    WallAwareGreedyPlayer,
    jev_body,
    make_player,
)
from system_one_control.rules import CompassRules
from tests.helpers import MAP

rules = CompassRules()


def turn(text: str) -> Turn:
    board = Board.parse(text)
    return Turn(board, rules, MAP.render(board, rules))


def test_random_picks_an_offered_move_and_is_reproducible():
    t = turn("#####\n#A.G#\n#####")
    assert RandomPlayer(seed=1).choose(t).move in rules.STEPS
    assert RandomPlayer(seed=1).choose(t).move == RandomPlayer(seed=1).choose(t).move


def test_the_solver_picks_a_best_move():
    assert SolverPlayer().choose(turn("#####\n#A#.#\n#.G.#\n#####")).move == "south"


def test_greedy_heads_for_the_key_first_then_the_goal():
    assert GreedyPlayer().choose(turn("#######\n#K.A.G#\n#######")).move == "west"
    assert GreedyPlayer().choose(turn("#######\n#..A.G#\n#######")).move == "east"


def test_greedy_walks_into_a_wall_that_stands_between_it_and_the_goal():
    assert GreedyPlayer().choose(turn("#####\n#A#G#\n#...#\n#####")).move == "east"


def test_greedy_with_walls_steps_around_instead():
    assert WallAwareGreedyPlayer().choose(turn("#####\n#A#G#\n#...#\n#####")).move == "south"


def test_greedy_breaks_ties_the_same_way_whatever_the_option_order():
    board = Board.parse("####\n#A.#\n#.G#\n####")
    requests = [MAP.render(board, rules, shuffle_seed=seed) for seed in "abcd"]
    moves = {GreedyPlayer().choose(Turn(board, rules, request)).move for request in requests}
    assert moves == {"south"}  # south and east both close in; south comes first in the rules


def test_players_are_built_by_name_and_only_jev_costs_money():
    assert isinstance(make_player("random"), RandomPlayer)
    assert {name for name, entry in PLAYERS.items() if entry.paid} == {"jev"}
    with pytest.raises(ValueError, match="unknown player"):
        make_player("chess-engine")


class FakeJevClient:
    def __init__(self, choice: str = "option_3", fail: Exception | None = None) -> None:
        self.choice, self.fail, self.sent = choice, fail, {}

    def system_one(self, *, state, questions, model):
        if self.fail:
            raise self.fail
        self.sent = {"state": state, "model": model, "questions": questions}
        probabilities = {"option_1": 0.1, "option_2": 0.1, "option_3": 0.7, "option_4": 0.1}
        answer = SimpleNamespace(choice=self.choice, probabilities=probabilities, confidence=0.6)
        usage = SimpleNamespace(input_tokens=120, output_tokens=3)
        return SimpleNamespace(choices={"move": answer}, usage=usage, model="jev-1.13.0")


def jev(client: FakeJevClient) -> JevPlayer:
    return JevPlayer(client=client)


def test_jev_is_sent_exactly_the_request_and_its_answer_maps_back_to_a_move():
    client = FakeJevClient()
    t = turn("#####\n#A.G#\n#####")
    choice = jev(client).choose(t)

    assert client.sent == jev_body(t.request)
    assert client.sent["state"] == t.request.state
    question = client.sent["questions"]["move"]
    assert question["type"] == "choice"
    assert question["instructions"] == t.request.question
    assert question["criteria"] == {o.id: o.text for o in t.request.options}
    assert choice.move == "east"
    assert choice.probabilities["east"] == 0.7
    assert choice.input_tokens == 120
    assert (choice.output_tokens, choice.confidence, choice.model) == (3, 0.6, "jev-1.13.0")


def test_a_failed_jev_call_is_raised_for_the_game_to_record():
    with pytest.raises(RuntimeError, match="rate limited"):
        jev(FakeJevClient(fail=RuntimeError("rate limited"))).choose(turn("####\n#AG#\n####"))


def test_jev_closes_only_a_client_it_opened_itself():
    jev(FakeJevClient()).close()  # the fake has no close(), so closing it would raise


def test_an_answer_outside_the_options_is_an_error():
    choice = jev(FakeJevClient(choice="option_9")).choose(turn("####\n#AG#\n####"))
    assert choice.move is None
    assert "option_9" in choice.error


def retry_until(error, succeed_on):
    """Run JEV_RETRY, without waits, on a call that raises `error` until attempt `succeed_on`."""
    attempts = []

    def call():
        attempts.append(error)
        if len(attempts) < succeed_on:
            raise error
        return "answered"

    retrying = build_tenacity(replace(JEV_RETRY, backoff_initial=0, backoff_max=0))
    try:
        return retrying(call), len(attempts)
    except TypeSafeError:
        return None, len(attempts)


def test_a_busy_server_is_tried_again_up_to_twice():
    busy = TypeSafeInternalServerError(529, {"error": "high traffic"}, httpx.Headers())
    assert retry_until(busy, succeed_on=3) == ("answered", 3)
    assert retry_until(busy, succeed_on=4) == (None, 3)


def test_a_timeout_or_a_bad_request_is_not_tried_again():
    assert retry_until(TypeSafeAPITimeoutError(60.0), succeed_on=2) == (None, 1)
    bad = TypeSafeBadRequestError(400, {"error": "bad"}, httpx.Headers())
    assert retry_until(bad, succeed_on=2) == (None, 1)


def test_the_retries_wait_about_one_second_then_two():
    assert (JEV_RETRY.backoff_initial, JEV_RETRY.backoff_max, JEV_RETRY.max_retries) == (1, 2, 2)

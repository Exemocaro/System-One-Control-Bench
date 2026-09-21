"""The Jev adapter's mapping, exercised against a fake client (no network)."""

from types import SimpleNamespace

import pytest

from system_one_control.agents.base import CandidateView, DecisionRequest
from system_one_control.agents.jev import API_KEY_NAMES, JevAgent
from system_one_control.observation import DYNAMICS_LEGEND

pytest.importorskip("typesafe_sdk", reason="Jev needs the models extra")


def _request(n=3):
    return DecisionRequest(
        request_id="r1",
        state="Agent: at (1, 1), facing east.",
        legend=DYNAMICS_LEGEND,
        question="Which option is best?",
        candidates=tuple(CandidateView(f"option_{i:03d}", f"do {i}") for i in range(n)),
    )


class _FakeClient:
    """Records what it was sent and replies with a scripted answer."""

    def __init__(self, choice="option_001", probabilities=None, confidence=0.9, error=None):
        self.sent = None
        self._choice = choice
        self._probabilities = probabilities or {
            "option_000": 0.05,
            "option_001": 0.9,
            "option_002": 0.05,
        }
        self._confidence = confidence
        self._error = error

    def system_one(self, state, questions, **kwargs):
        self.sent = {"state": state, "questions": questions, "kwargs": kwargs}
        if self._error is not None:
            raise self._error
        answer = SimpleNamespace(
            choice=self._choice,
            probabilities=self._probabilities,
            confidence=self._confidence,
            type="choice",
        )
        return SimpleNamespace(
            model="jev-1.13.0",
            choices={"action": answer},
            usage=SimpleNamespace(input_tokens=357, output_tokens=54),
        )


def _agent(client, **kwargs):
    return JevAgent(api_key="test-key", client=client, **kwargs)


def test_the_menu_becomes_the_criteria_of_one_choice_question():
    client = _FakeClient()
    _agent(client).choose(_request())
    question = client.sent["questions"]["action"]
    assert set(question.criteria) == {"option_000", "option_001", "option_002"}
    assert question.criteria["option_001"] == "do 1"


def test_the_instructions_are_the_benchmark_question_verbatim():
    client = _FakeClient()
    request = _request()
    _agent(client).choose(request)
    assert client.sent["questions"]["action"].instructions == request.question


def test_the_rules_legend_travels_with_the_state():
    """A model asked without the rules is being tested on guessing them."""
    client = _FakeClient()
    request = _request()
    _agent(client).choose(request)
    assert DYNAMICS_LEGEND in client.sent["state"]
    assert request.state in client.sent["state"]


def test_the_answer_becomes_a_decision_result():
    result = _agent(_FakeClient()).choose(_request())
    assert result.selected_display_id == "option_001"
    assert result.confidence == 0.9
    assert result.probabilities["option_001"] == 0.9
    assert result.usage == {"input_tokens": 357, "output_tokens": 54}
    assert result.error is None
    assert result.agent == "jev"


def test_the_model_that_answered_is_recorded():
    result = _agent(_FakeClient()).choose(_request())
    assert result.extra["model"] == "jev-1.13.0"


def test_an_answer_outside_the_menu_is_an_error_not_a_choice():
    result = _agent(_FakeClient(choice="option_999")).choose(_request())
    assert result.selected_display_id is None
    assert "option_999" in result.error


def test_no_model_is_named_unless_one_was_asked_for():
    client = _FakeClient()
    _agent(client).choose(_request())
    assert "model" not in client.sent["kwargs"]

    pinned = _FakeClient()
    _agent(pinned, model="jev-1.13.0").choose(_request())
    assert pinned.sent["kwargs"]["model"] == "jev-1.13.0"


def test_a_rate_limit_is_retried():
    class _RateLimited(_FakeClient):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def system_one(self, state, questions, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise type("TypeSafeRateLimitError", (Exception,), {})("slow down")
            return super().system_one(state, questions, **kwargs)

    client = _RateLimited()
    result = _agent(client, max_attempts=3).choose(_request())
    assert result.selected_display_id == "option_001"
    assert client.calls == 2


def test_an_authentication_failure_is_recorded_rather_than_raised():
    error = type("TypeSafeAuthenticationError", (Exception,), {})("bad key")
    result = _agent(_FakeClient(error=error), max_attempts=1).choose(_request())
    assert result.selected_display_id is None
    assert "bad key" in result.error


def test_jev_is_never_privileged():
    assert _agent(_FakeClient()).privileged is False


def test_the_key_is_looked_up_under_both_names():
    assert "JEV_API_KEY" in API_KEY_NAMES
    assert "TYPESAFE_API_KEY" in API_KEY_NAMES


def test_jev_is_selectable_by_name():
    from system_one_control.agents.registry import DEFAULT_REGISTRY

    assert "jev" in DEFAULT_REGISTRY


def test_a_bad_key_is_not_retried():
    """Retrying an authentication failure cannot help and costs three round trips."""

    class _AlwaysUnauthorised(_FakeClient):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def system_one(self, state, questions, **kwargs):
            self.calls += 1
            raise type("TypeSafeAuthenticationError", (Exception,), {})("bad key")

    client = _AlwaysUnauthorised()
    result = _agent(client, max_attempts=3).choose(_request())
    assert result.selected_display_id is None
    assert client.calls == 1
    assert "bad key" in result.error

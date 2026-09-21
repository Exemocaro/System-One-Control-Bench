"""The shared model-adapter machinery, exercised without touching a network."""

from system_one_control.agents.base import CandidateView, DecisionRequest
from system_one_control.agents.model import ModelAgent, ModelAnswer, ModelCallError


def _request(n=3):
    return DecisionRequest(
        request_id="r1",
        state="state text",
        legend="legend text",
        question="question text",
        candidates=tuple(CandidateView(f"option_{i:03d}", f"do {i}") for i in range(n)),
    )


class _Scripted(ModelAgent):
    """A model whose replies are written in advance."""

    def __init__(self, replies, **kwargs):
        super().__init__(name="scripted", **kwargs)
        self.replies = list(replies)
        self.calls = 0

    def call_model(self, request):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_a_valid_answer_becomes_a_decision_result():
    agent = _Scripted([ModelAnswer(selected_display_id="option_001", confidence=0.8)])
    result = agent.choose(_request())
    assert result.selected_display_id == "option_001"
    assert result.confidence == 0.8
    assert result.error is None
    assert result.agent == "scripted"


def test_latency_is_measured_rather_than_reported_by_the_model():
    agent = _Scripted([ModelAnswer(selected_display_id="option_000")])
    assert agent.choose(_request()).latency_ms > 0


def test_an_option_the_menu_never_offered_is_recorded_as_an_error():
    """A model naming an id that was not on the menu is a failure, not a choice."""
    agent = _Scripted([ModelAnswer(selected_display_id="option_999")] * 3)
    result = agent.choose(_request())
    assert result.selected_display_id is None
    assert "option_999" in result.error


def test_a_transient_failure_is_retried_and_then_succeeds():
    agent = _Scripted(
        [ModelCallError("timeout"), ModelAnswer(selected_display_id="option_002")],
        max_attempts=3,
    )
    result = agent.choose(_request())
    assert result.selected_display_id == "option_002"
    assert result.attempt_count == 2
    assert agent.calls == 2


def test_retries_stop_at_the_limit_and_the_last_error_is_kept():
    agent = _Scripted([ModelCallError("down")] * 5, max_attempts=3)
    result = agent.choose(_request())
    assert result.selected_display_id is None
    assert result.attempt_count == 3
    assert agent.calls == 3
    assert "down" in result.error


def test_an_unexpected_exception_is_captured_rather_than_ending_the_run():
    """One bad decision must not destroy the records already written."""
    agent = _Scripted([RuntimeError("something else")], max_attempts=1)
    result = agent.choose(_request())
    assert result.selected_display_id is None
    assert "something else" in result.error


def test_probabilities_are_kept_only_for_options_that_were_offered():
    answer = ModelAnswer(
        selected_display_id="option_000",
        probabilities={"option_000": 0.5, "option_001": 0.3, "ghost": 0.2},
    )
    result = _Scripted([answer]).choose(_request())
    assert set(result.probabilities) == {"option_000", "option_001"}


def test_a_model_agent_is_never_privileged():
    assert _Scripted([]).privileged is False


def test_usage_is_carried_through_for_cost_accounting():
    answer = ModelAnswer(
        selected_display_id="option_000", usage={"input_tokens": 12, "output_tokens": 3}
    )
    assert _Scripted([answer]).choose(_request()).usage == {"input_tokens": 12, "output_tokens": 3}


def test_an_empty_menu_is_refused_before_any_call_is_made():
    agent = _Scripted([])
    result = agent.choose(_request(n=0))
    assert result.selected_display_id is None
    assert agent.calls == 0

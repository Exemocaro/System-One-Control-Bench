"""Jev, via the TypeSafe Python SDK.

Jev answers a typed Choice question directly, so the menu maps onto `criteria`
without any parsing: the option ids the benchmark generated are the option names
the model returns, and a malformed answer is not a failure mode that exists.

The SDK is an optional dependency. Importing this module without it is fine;
only constructing the agent fails, and with a message saying what to install.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from system_one_control.agents.base import DecisionRequest
from system_one_control.agents.model import (
    ModelAgent,
    ModelAnswer,
    ModelCallError,
    ModelRefusedError,
)
from system_one_control.credentials import load_api_key

if TYPE_CHECKING:  # pragma: no cover
    pass

# Whatever the account's key is filed under. Theirs first, then the name the
# TypeSafe console suggests.
API_KEY_NAMES = ("TYPESAFE_API_KEY", "JEV_API_KEY")

QUESTION_NAME = "action"
INSTALL_HINT = "Jev needs the TypeSafe SDK: uv sync --extra models"

# Retrying is worthwhile for these and pointless for the rest.
RETRYABLE_ERRORS = (
    "TypeSafeRateLimitError",
    "TypeSafeInternalServerError",
    "TypeSafeAPIConnectionError",
    "TypeSafeAPITimeoutError",
)


def _import_sdk() -> tuple[Any, Any]:
    try:
        from typesafe_sdk import Choice, TypeSafeClient
    except ImportError as error:  # pragma: no cover - depends on the install
        raise ImportError(f"{INSTALL_HINT} ({error})") from error
    return Choice, TypeSafeClient


class JevAgent(ModelAgent):
    """A bounded decision model that picks one of the offered options."""

    def __init__(
        self,
        *,
        name: str = "jev",
        model: str | None = None,
        api_key: str | None = None,
        max_attempts: int = 3,
        timeout_seconds: float = 60.0,
        client: Any | None = None,
    ) -> None:
        super().__init__(name=name, max_attempts=max_attempts, timeout_seconds=timeout_seconds)
        self.model = model
        self._choice, client_type = _import_sdk()
        self._client = client or client_type(
            api_key=api_key or load_api_key(*API_KEY_NAMES),
            timeout=timeout_seconds,
        )

    def call_model(self, request: DecisionRequest) -> ModelAnswer:
        try:
            response = self._client.system_one(
                state=self._state_for(request),
                questions={
                    QUESTION_NAME: self._choice(
                        instructions=request.question,
                        criteria={c.display_id: c.description for c in request.candidates},
                    )
                },
                **({"model": self.model} if self.model else {}),
            )
        except Exception as error:
            label = f"{type(error).__name__}: {error}"
            if type(error).__name__ in RETRYABLE_ERRORS:
                raise ModelCallError(label) from error
            # A bad key or a malformed request fails the same way every time.
            raise ModelRefusedError(label) from error

        answer = response.choices[QUESTION_NAME]
        return ModelAnswer(
            selected_display_id=answer.choice,
            probabilities=dict(answer.probabilities),
            confidence=answer.confidence,
            usage=self._usage_of(response),
            extra={"model": str(getattr(response, "model", "") or "")},
        )

    def _state_for(self, request: DecisionRequest) -> str:
        """The rules travel with the state; the question carries the menu."""
        return f"{request.legend}\n\n{request.state}"

    @staticmethod
    def _usage_of(response: Any) -> dict[str, int] | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        counted = {name: getattr(usage, name, None) for name in ("input_tokens", "output_tokens")}
        return {k: int(v) for k, v in counted.items() if v is not None} or None

    def close(self) -> None:
        closer = getattr(self._client, "close", None)
        if closer is not None:
            closer()

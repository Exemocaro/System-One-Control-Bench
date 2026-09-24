from __future__ import annotations

import os
import re
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, ClassVar

import httpx
from dotenv import load_dotenv

from system_one_control.players import Choice, Player, Turn, answer_choice, with_retries
from system_one_control.request import Request

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_KEY_NAME = "OPENROUTER_API_KEY"

# Short names for OpenRouter models. Chosen in September 2026 as the cheapest recent chat models
# whose reasoning can be switched off, so each plays both with and without it. Pinned versions
# rather than "latest" aliases, so a run can be repeated. Prices are per million tokens.
LLM_MODELS = {
    "ling-3.0-flash": "inclusionai/ling-3.0-flash",  # $0.021 in, $0.063 out
    "qwen3.7-flash": "qwen/qwen3.7-flash",  # $0.03 in, $0.13 out
    "deepseek-v4-flash": "deepseek/deepseek-v4-flash-0731",  # $0.03 in, $0.32 out
    "nemotron-3.5-lightning": "nvidia/nemotron-3.5-lightning",  # $0.08 in, $0.20 out
    "gemma-4-26b": "google/gemma-4-26b-a4b-it",  # $0.09 in, $0.30 out
    "gpt-6-luna": "openai/gpt-6-luna",  # $0.10 in, $0.50 out
}

LLM_SYSTEM = (
    "You are playing a puzzle on a grid. You are given the state of the game, a question and "
    "a list of options, each with an id such as option_3. Reply with the id of the one option "
    "you choose, and nothing else."
)
# Seconds to wait before each retry of a request the provider turned away.
LLM_RETRY_WAITS = (1.0, 2.0)
# Answering without reasoning is a few tokens, such as "option_12"; the cap stops a model that
# reasons anyway from running up a bill, and its answer then comes back empty, as an error.
ANSWER_TOKENS = 64
# Seconds a call may take: reasoning can take minutes on a long puzzle.
LLM_TIMEOUT = 120.0
LLM_REASONING_TIMEOUT = 600.0

OPTION_ID = re.compile(r"option_\d+")


class ProviderError(Exception):
    """An error OpenRouter reported inside an answer it sent with a success status."""

    def __init__(self, code: int | None, message: str) -> None:
        super().__init__(f"{code} {message}")
        self.code = code


def openrouter_key() -> str:
    load_dotenv()
    key = os.environ.get(OPENROUTER_KEY_NAME)
    if not key:
        raise RuntimeError(f"no OpenRouter API key: set {OPENROUTER_KEY_NAME} in .env")
    return key


def turned_away(error: Exception) -> bool:
    """Whether the provider refused the request (busy, rate-limited, failing) or never got it.

    As for Jev, a timeout is not one of these: the provider may have answered, and billed, it.
    """
    if isinstance(error, httpx.TimeoutException):
        return False
    if isinstance(error, httpx.TransportError):
        return True
    if isinstance(error, httpx.HTTPStatusError):
        code: int | None = error.response.status_code
    elif isinstance(error, ProviderError):
        code = error.code
    else:
        return False
    return code is not None and (code == 429 or code >= 500)


def llm_messages(request: Request) -> list[dict[str, str]]:
    """The chat sent for a request: its state, question and options, as Jev is sent them."""
    options = "\n".join(f"{option.id}: {option.text}" for option in request.options)
    user = f"{request.state}\n\n{request.question}\n\nOptions:\n{options}"
    return [{"role": "system", "content": LLM_SYSTEM}, {"role": "user", "content": user}]


def parse_answer(text: str, request: Request) -> str | None:
    """The last option id in the answer that is one of the request's, or None."""
    ids = {option.id for option in request.options}
    found = [match for match in OPTION_ID.findall(text) if match in ids]
    return found[-1] if found else None


class LLMPlayer(Player):
    """A chat model on OpenRouter, asked for the id of one option. Sees only the request.

    With `reasoning` off it must answer at once, as Jev does; with it on, it may think first,
    which is slower and costs more. A chat answer carries no probabilities, so none are kept.
    Retries follow Jev's: a call the provider turned away is tried again after each wait.
    """

    name: ClassVar[str] = "llm"

    def __init__(
        self,
        model: str,
        *,
        reasoning: bool,
        client: Any = None,
        retry_waits: Sequence[float] = LLM_RETRY_WAITS,
    ) -> None:
        self._owns_client = client is None
        if client is None:
            timeout = LLM_REASONING_TIMEOUT if reasoning else LLM_TIMEOUT
            headers = {"Authorization": f"Bearer {openrouter_key()}"}
            client = httpx.Client(headers=headers, timeout=timeout)
        self.model = model
        self.reasoning = reasoning
        self._client = client
        self._retry_waits = tuple(retry_waits)

    def body(self, request: Request) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": llm_messages(request),
            # The reasoning is billed either way; leaving its text out only saves the transfer.
            "reasoning": {"enabled": self.reasoning, "exclude": True},
            "usage": {"include": True},  # adds the cost to the answer
        }
        if not self.reasoning:
            body["max_tokens"] = ANSWER_TOKENS
        return body

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(OPENROUTER_URL, json=body)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        if "error" in data:
            error = data["error"]
            raise ProviderError(error.get("code"), error.get("message", ""))
        return data

    def choose(self, turn: Turn) -> Choice:
        body = self.body(turn.request)
        data, seconds, retried = with_retries(
            lambda: self._post(body), self._retry_waits, turned_away
        )
        text = data["choices"][0]["message"].get("content") or ""
        usage = data.get("usage") or {}
        provider = data.get("provider")
        model = data.get("model", self.model)
        choice = answer_choice(
            turn.request,
            parse_answer(text, turn.request),
            {},
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            model=f"{model} via {provider}" if provider else model,
            seconds=seconds,
            retried=retried,
            cost=usage.get("cost"),
        )
        if choice.error:
            return replace(choice, error=f"{self.model} answered {text[:200]!r}")
        return choice

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

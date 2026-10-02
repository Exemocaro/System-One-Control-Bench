from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

import httpx

from system_one_control.players import (
    Choice,
    Player,
    Turn,
    answer_choice,
    api_key,
    with_retries,
)
from system_one_control.prompts import Request

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_KEY_NAME = "OPENROUTER_API_KEY"

# Short names for chat models on OpenRouter, each with the one host that runs it; each plays
# with its reasoning off and on. Pinned versions rather than "latest" aliases, and one host
# rather than whichever is free, as hosts may run a model differently: a run can be repeated.
# Gemma 4 26B was among the cheapest recent models whose reasoning can be switched off in
# September 2026, at $0.09 per million input tokens and $0.30 per million output tokens;
# DeepSeek V4.1 Flash is a bigger model at $0.14 and $0.42 on DeepInfra. `openrouter.ai/models`
# has others.
LLM_MODELS = {
    "gemma-4-26b": ("google/gemma-4-26b-a4b-it", "deepinfra"),
    "deepseek-v4.1-flash": ("deepseek/deepseek-v4.1-flash", "deepinfra"),
}

LLM_SYSTEM = (
    "You are playing a puzzle on a grid. You are given the state of the game, a question and "
    "a list of options, each with an id such as option_3. Reply with the id of the one option "
    "you choose."
)
# Seconds to wait before each retry of a request the provider turned away. Longer than Jev's:
# OpenRouter shares each model's capacity, and a rate limit there lasts tens of seconds.
LLM_RETRY_WAITS = (5.0, 15.0, 30.0, 60.0)
# Answering without reasoning is a few tokens, such as {"option": "option_12"}; the cap stops a
# model that reasons anyway from running up a bill, and its answer then comes back cut, as an error.
ANSWER_TOKENS = 64
# With reasoning, the thinking is capped: on a level-10 request DeepSeek V4.1 Flash used 748 tokens
# under this budget, 1,361 under 2,048 and 2,400 at effort "low", which would have tripled the cost.
REASONING_BUDGET = 1024
# Seconds a call may take: reasoning can take minutes on a long puzzle.
LLM_TIMEOUT = 120.0
LLM_REASONING_TIMEOUT = 600.0

OPTION_ID = re.compile(r"option_\d+")


class ProviderError(Exception):
    """An error OpenRouter reported inside an answer it sent with a success status."""

    def __init__(self, code: int | None, message: str) -> None:
        super().__init__(f"{code} {message}")
        self.code = code


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


def answer_format(request: Request) -> dict[str, Any]:
    """A JSON schema that allows only an answer naming one of the options."""
    option = {"type": "string", "enum": [option.id for option in request.options]}
    schema = {
        "type": "object",
        "properties": {"option": option},
        "required": ["option"],
        "additionalProperties": False,
    }
    return {
        "type": "json_schema",
        "json_schema": {"name": "answer", "strict": True, "schema": schema},
    }


def parse_answer(text: str, request: Request) -> str | None:
    """The option the answer names, or None: the JSON it was asked for, or failing that the
    last option id in the text that is one of the request's."""
    ids = {option.id for option in request.options}
    try:
        answer = json.loads(text)
    except json.JSONDecodeError:
        answer = None
    if isinstance(answer, dict) and answer.get("option") in ids:
        return str(answer["option"])
    found = [match for match in OPTION_ID.findall(text) if match in ids]
    return found[-1] if found else None


class LLMPlayer(Player):
    """A chat model on OpenRouter, asked for the id of one option. Sees only the request.

    With `reasoning` off it must answer at once, as Jev does; with it on, it may think first,
    which is slower and costs more. A chat answer carries no probabilities, so none are kept.
    Retries follow Jev's: a call the provider turned away is tried again after each wait.
    """

    def __init__(
        self,
        model: str,
        *,
        reasoning: bool,
        host: str | None = None,
        client: Any = None,
        retry_waits: Sequence[float] = LLM_RETRY_WAITS,
    ) -> None:
        self._owns_client = client is None
        if client is None:
            timeout = LLM_REASONING_TIMEOUT if reasoning else LLM_TIMEOUT
            headers = {"Authorization": f"Bearer {api_key([OPENROUTER_KEY_NAME], 'OpenRouter')}"}
            client = httpx.Client(headers=headers, timeout=timeout)
        self.model = model
        self.host = host
        self.reasoning = reasoning
        self._client = client
        self._retry_waits = tuple(retry_waits)

    def body(self, request: Request) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": llm_messages(request),
            # The reasoning is billed either way; leaving its text out only saves the transfer.
            "reasoning": {"enabled": self.reasoning, "exclude": True}
            | ({"max_tokens": REASONING_BUDGET} if self.reasoning else {}),
            "usage": {"include": True},  # adds the cost to the answer
            # The answer must be JSON naming one of the options, so a model cannot answer in
            # prose, or think aloud when its reasoning is off; only providers that enforce it.
            "response_format": answer_format(request),
            "provider": {"require_parameters": True},
        }
        if self.host:
            body["provider"] |= {"order": [self.host], "allow_fallbacks": False}
        body["max_tokens"] = REASONING_BUDGET + ANSWER_TOKENS if self.reasoning else ANSWER_TOKENS
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
        answer = data["choices"][0]
        text = answer["message"].get("content") or ""
        # A cut-off answer can still hold a valid id, such as option_1 out of option_12.
        cut = answer.get("finish_reason") == "length"
        usage = data.get("usage") or {}
        provider = data.get("provider")
        model = data.get("model", self.model)
        choice = answer_choice(
            turn.request,
            None if cut else parse_answer(text, turn.request),
            {},
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            model=f"{model} via {provider}" if provider else model,
            seconds=seconds,
            retried=retried,
            cost=usage.get("cost"),
        )
        if choice.error:
            how = "ran out of tokens after" if cut else "answered"
            return replace(choice, error=f"{self.model} {how} {text[:200]!r}")
        return choice

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

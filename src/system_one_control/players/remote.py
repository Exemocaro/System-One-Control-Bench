"""Players over the network: Jev, chat models on OpenRouter, and their shared helpers."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Any, TypeVar

import httpx
from typesafe_sdk import (
    RetryPolicy,
    TypeSafeAPIConnectionError,
    TypeSafeAPITimeoutError,
    TypeSafeClient,
    TypeSafeInternalServerError,
    TypeSafeRateLimitError,
)

from system_one_control.players.base import (
    Choice,
    Player,
    Turn,
    answer_choice,
)
from system_one_control.players.base import (
    api_key as lookup_key,
)
from system_one_control.prompts import Request

JEV_MODEL = "jev-1.13.0"
JEV_QUESTION = "move"
API_KEY_NAMES = ("TYPESAFE_API_KEY", "JEV_API_KEY")
# Seconds to wait before each retry of a request the server turned away.
JEV_RETRY_WAITS = (1.0, 2.0)
# Seconds a call may take. A timeout is not retried and ends the game, so this is generous:
# the slowest compass call took 39 s, and a three-moves request is about 5 times as long.
JEV_TIMEOUT = 120.0


def server_turned_away(error: Exception) -> bool:
    """Whether Jev refused the request (busy, rate-limited, failing) or never got it.

    A timeout is not one of these: the server may have answered, and billed, a slow request.
    """
    if isinstance(error, TypeSafeAPITimeoutError):
        return False
    refused = (TypeSafeRateLimitError, TypeSafeInternalServerError, TypeSafeAPIConnectionError)
    return isinstance(error, refused)


T = TypeVar("T")


def with_retries(
    call: Callable[[], T],
    waits: Sequence[float],
    retryable: Callable[[Exception], bool],
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[T, float, tuple[str, ...]]:
    """Make a call, trying again after each of `waits` while it fails in a way worth retrying.

    Returns what the call returned, how many seconds the answering call alone took, and why
    each earlier attempt failed. The last failure, or any not worth retrying, is raised.
    """
    retried: list[str] = []
    for wait in (*waits, None):
        started = time.perf_counter()
        try:
            result = call()
        except Exception as error:
            if wait is None or not retryable(error):
                raise
            retried.append(f"{type(error).__name__}: {error}")
            sleep(wait)
            continue
        return result, time.perf_counter() - started, tuple(retried)
    raise AssertionError("unreachable: the last attempt returns or raises")


def jev_body(request: Request, model: str = JEV_MODEL) -> dict[str, Any]:
    """The JSON body sent to Jev for a request, exactly as it goes over the wire."""
    return {
        "state": request.state,
        "model": model,
        "questions": {
            JEV_QUESTION: {
                "type": "choice",
                "instructions": request.question,
                "criteria": {option.id: option.text for option in request.options},
            }
        },
    }


class JevPlayer(Player):
    """Jev, through the TypeSafe SDK. Sees only the request, never the board.

    A call the server turned away is tried again after each of `retry_waits`, and the choice
    records why each earlier attempt failed. Its time is the answering call's alone. A call
    that still fails raises, and the game records it as a move with no answer.
    """

    def __init__(
        self,
        model: str = JEV_MODEL,
        client: Any = None,
        retry_waits: Sequence[float] = JEV_RETRY_WAITS,
    ) -> None:
        self._owns_client = client is None
        if client is None:
            no_retries = RetryPolicy(max_retries=0)  # retried here, so each attempt is seen
            client = TypeSafeClient(
                api_key=lookup_key(API_KEY_NAMES, "Jev"), timeout=JEV_TIMEOUT, retry=no_retries
            )
        self.model = model
        self._client = client
        self._retry_waits = tuple(retry_waits)

    def choose(self, turn: Turn) -> Choice:
        body = jev_body(turn.request, self.model)
        response, seconds, retried = with_retries(
            lambda: self._client.system_one(**body), self._retry_waits, server_turned_away
        )
        answer = response.choices[JEV_QUESTION]
        return answer_choice(
            turn.request,
            answer.choice,
            answer.probabilities,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            confidence=answer.confidence,
            model=response.model,
            seconds=seconds,
            retried=retried,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


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

# Frozen prompt text: sent to chat models verbatim, so changing it changes results.
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


def provider_turned_away(error: Exception) -> bool:
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


def chat_payload(request: Request, reasoning: bool) -> dict[str, Any]:
    """The body sent to OpenRouter for a request, apart from the model and host choices."""
    return {
        "messages": llm_messages(request),
        # The reasoning is billed either way; leaving its text out only saves the transfer.
        "reasoning": {"enabled": reasoning, "exclude": True}
        | ({"max_tokens": REASONING_BUDGET} if reasoning else {}),
        "usage": {"include": True},  # adds the cost to the answer
        # The answer must be JSON naming one of the options, so a model cannot answer in
        # prose, or think aloud when its reasoning is off; only providers that enforce it.
        "response_format": answer_format(request),
        "provider": {"require_parameters": True},
        "max_tokens": REASONING_BUDGET + ANSWER_TOKENS if reasoning else ANSWER_TOKENS,
    }


class HTTPPlayer(Player):
    """A player that asks over HTTP with retries. Subclasses implement body() and choose()."""

    def __init__(
        self,
        *,
        api_key: str | None,
        timeout: float,
        retry_waits: Sequence[float],
        client: Any = None,
    ) -> None:
        self._owns_client = client is None
        if client is None:
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            client = httpx.Client(headers=headers, timeout=timeout)
        self._client = client
        self._retry_waits = tuple(retry_waits)

    def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(url, json=body)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


class LLMPlayer(HTTPPlayer):
    """A chat model on OpenRouter, asked for the id of one option. Sees only the request.

    With `reasoning` off it must answer at once, as Jev does; with it on, it may think first,
    which is slower and costs more. A chat answer carries no probabilities, so none are kept.
    Retries follow Jev's: a call the provider turned away is tried again after each wait.
    Any OpenAI-compatible endpoint works through `base_url`, but only OpenRouter gets its
    provider, usage and reasoning fields.
    """

    def __init__(
        self,
        model: str,
        *,
        reasoning: bool,
        host: str | None = None,
        client: Any = None,
        retry_waits: Sequence[float] = LLM_RETRY_WAITS,
        base_url: str = OPENROUTER_URL,
        api_key: str | None = None,
    ) -> None:
        if api_key is None and base_url == OPENROUTER_URL:
            api_key = lookup_key([OPENROUTER_KEY_NAME], "OpenRouter")
        super().__init__(
            api_key=api_key,
            timeout=LLM_REASONING_TIMEOUT if reasoning else LLM_TIMEOUT,
            retry_waits=retry_waits,
            client=client,
        )
        self.model = model
        self.host = host
        self.reasoning = reasoning
        self.base_url = base_url

    def body(self, request: Request) -> dict[str, Any]:
        body: dict[str, Any] = {"model": self.model, **chat_payload(request, self.reasoning)}
        if self.base_url == OPENROUTER_URL:
            if self.host:
                body["provider"] |= {"order": [self.host], "allow_fallbacks": False}
        else:
            for key in ("provider", "usage", "reasoning"):
                del body[key]
        return body

    def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        data = super()._post(url, body)
        if "error" in data:
            error = data["error"]
            if not isinstance(error, dict):
                error = {"code": None, "message": str(error)}
            raise ProviderError(error.get("code"), error.get("message", ""))
        return data

    def choose(self, turn: Turn) -> Choice:
        body = self.body(turn.request)
        data, seconds, retried = with_retries(
            lambda: self._post(self.base_url, body), self._retry_waits, provider_turned_away
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


class DecisionPlayer(HTTPPlayer):
    """A bounded decision model behind an HTTP API. Sees only the request.

    It is sent the state, the question and the options with their ids, and answers either
    probabilities for each id, of which the likeliest is played, or one id outright.
    Retries follow the chat players'. See SUBMITTING.md for the contract.
    """

    def __init__(
        self,
        url: str,
        *,
        api_key: str | None = None,
        client: Any = None,
        retry_waits: Sequence[float] = LLM_RETRY_WAITS,
    ) -> None:
        super().__init__(
            api_key=api_key, timeout=LLM_TIMEOUT, retry_waits=retry_waits, client=client
        )
        self.url = url

    def body(self, request: Request) -> dict[str, Any]:
        """The JSON sent for a request: the state, the question and the options by id."""
        return {
            "state": request.state,
            "question": request.question,
            "options": [{"id": option.id, "text": option.text} for option in request.options],
        }

    def choose(self, turn: Turn) -> Choice:
        body = self.body(turn.request)
        data, seconds, retried = with_retries(
            lambda: self._post(self.url, body), self._retry_waits, provider_turned_away
        )
        probabilities = data.get("probabilities") or {}
        if probabilities:
            option_id = max(sorted(probabilities), key=probabilities.__getitem__)
        elif data.get("choice") is not None:
            option_id, probabilities = data["choice"], {}
        else:
            return Choice(None, error=f"answered neither probabilities nor choice: {data!r}"[:210])
        return answer_choice(
            turn.request, option_id, probabilities, seconds=seconds, retried=retried
        )

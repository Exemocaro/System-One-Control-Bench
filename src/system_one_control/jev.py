from __future__ import annotations

import os
from typing import Any

from system_one_control.players import Choice, Player, Turn

MODEL = "jev-1.13.0"
QUESTION = "move"
API_KEY_NAMES = ("TYPESAFE_API_KEY", "JEV_API_KEY")


def api_key() -> str:
    from dotenv import load_dotenv

    load_dotenv()
    for name in API_KEY_NAMES:
        if os.environ.get(name):
            return os.environ[name]
    raise RuntimeError(f"no Jev API key: set {' or '.join(API_KEY_NAMES)} in .env")


class JevPlayer(Player):
    """Jev, through the TypeSafe SDK. Sees only the request, never the board."""

    name = "jev"

    def __init__(self, model: str = MODEL, client: Any = None, question_type: Any = None) -> None:
        if client is None or question_type is None:
            from typesafe_sdk import Choice as JevQuestion
            from typesafe_sdk import RetryPolicy, TypeSafeClient

            no_retries = RetryPolicy(max_retries=0)  # one move is exactly one paid call
            client = client or TypeSafeClient(api_key=api_key(), timeout=60.0, retry=no_retries)
            question_type = question_type or JevQuestion
        self.model = model
        self._client = client
        self._question_type = question_type

    def choose(self, turn: Turn) -> Choice:
        request = turn.request
        question = self._question_type(
            instructions=request.question,
            criteria={option.id: option.text for option in request.options},
        )
        try:
            response = self._client.system_one(
                state=request.state, questions={QUESTION: question}, model=self.model
            )
        except Exception as error:
            return Choice(None, error=f"{type(error).__name__}: {error}")

        answer = response.choices[QUESTION]
        moves = {option.id: option.move for option in request.options}
        probabilities = {moves[id]: p for id, p in answer.probabilities.items() if id in moves}
        if answer.choice not in moves:
            return Choice(None, probabilities, error=f"Jev answered {answer.choice!r}")
        return Choice(moves[answer.choice], probabilities)

"""Example bounded-decision-model server: uniform probabilities over the options."""

from typing import Any

from fastapi import FastAPI

app = FastAPI()


@app.post("/decide")
def decide(body: dict[str, Any]) -> dict[str, Any]:
    options = body["options"]
    each = 1 / len(options)
    return {"probabilities": {option["id"]: each for option in options}}

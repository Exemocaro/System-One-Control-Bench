"""Decision models that run on this machine: free, but they need `uv sync --extra local`.

Each model is loaded once per process, the first time a game asks it anything, and every game
shares it. Only one answer is worked out at a time: the model already uses every core, or the
GPU, so games side by side would only wait for each other.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from typing import Any, ClassVar

from system_one_control.players import Choice, Player, Turn, answer_choice
from system_one_control.request import Request

DEVICE_NAME = "SOCB_DEVICE"  # such as cpu or cuda; by default the model picks

LAYA_REPO = "convaiinnovations/laya"
LAYA_CHECKPOINT = "typed-decisions"  # 1,024 tokens by default, stretched here as needed
# Laya reads at most this many tokens, and cuts every option to LAYA_OPTION_TOKENS.
LAYA_MAX_TOKENS = 8192
LAYA_OPTION_TOKENS = 48

GLICLASS_MODEL = "knowledgator/gliclass-modern-large-v3.0"  # ModernBERT-large, as Laya is
GLICLASS_MAX_TOKENS = 8192

_models: dict[str, Any] = {}
_loading = threading.Lock()
_running = threading.Lock()


def device() -> str | None:
    return os.environ.get(DEVICE_NAME) or None


def shared(name: str, load: Callable[[], Any]) -> Any:
    """The model loaded under this name, loading it the first time it is asked for."""
    with _loading:
        if name not in _models:
            _models[name] = load()
        return _models[name]


def load_laya() -> Any:
    import laya  # an optional dependency: uv sync --extra local

    return laya.load(LAYA_REPO, subfolder=LAYA_CHECKPOINT, device=device())


def laya_budget(count: Callable[[str], int], request: Request) -> tuple[int, int]:
    """The token budgets that let Laya read the whole request: (max_len, head_max_len).

    Laya puts the question and every option first, in a part of head_max_len tokens, then as
    much of the state as fits in max_len. Where either is too small it cuts the text short
    without saying so, so both are worked out from the request. An option longer than Laya
    ever reads is refused rather than cut.
    """
    options = [count(" " + option.text) for option in request.options]
    too_long = [
        o.text
        for o, tokens in zip(request.options, options, strict=True)
        if tokens > LAYA_OPTION_TOKENS
    ]
    if too_long:
        raise ValueError(
            f"Laya reads {LAYA_OPTION_TOKENS} tokens of an option, and {len(too_long)} are "
            f"longer, such as {too_long[0]!r}"
        )
    question = count(f"choice question: {request.question}")
    # One marker per option, and the 16 tokens Laya keeps spare or else squeezes the options.
    head = question + sum(tokens + 1 for tokens in options) + 16
    total = head + count(request.state) + 8  # [CLS], separators, and some to spare
    if total > LAYA_MAX_TOKENS:
        raise ValueError(f"the request is {total} Laya tokens, more than its {LAYA_MAX_TOKENS}")
    return total, head


class LayaPlayer(Player):
    """Laya's typed-decisions checkpoint, an open-weight model built to answer as Jev does.

    It is asked Jev's question, but with the options as a list of their texts: Laya would
    write each option's id in front of its text, and the ids mean nothing, while an option
    gets only 48 tokens. Sees only the request.
    """

    name: ClassVar[str] = "laya"

    def __init__(self, agent: Any = None) -> None:
        self._agent = agent  # for tests; otherwise the shared model

    def choose(self, turn: Turn) -> Choice:
        request = turn.request
        agent = self._agent or shared("laya", load_laya)
        max_len, head_max_len = laya_budget(
            lambda text: len(agent.tok(text, add_special_tokens=False)["input_ids"]), request
        )
        question = {
            "type": "choice",
            "instructions": request.question,
            "criteria": [option.text for option in request.options],
        }
        with _running:
            started = time.perf_counter()
            result = agent.system_one(
                request.state, {"move": question}, max_len=max_len, head_max_len=head_max_len
            )
            seconds = time.perf_counter() - started
        answer = result["answers"]["move"]
        ids = {option.text: option.id for option in request.options}
        return answer_choice(
            request,
            ids.get(answer["choice"]),
            {ids[text]: p for text, p in answer["probabilities"].items() if text in ids},
            input_tokens=result.get("usage", {}).get("input_tokens"),
            confidence=answer.get("confidence"),
            model=f"laya-{LAYA_CHECKPOINT}",
            seconds=seconds,
        )


def load_gliclass() -> Any:
    # Optional dependencies: uv sync --extra local
    import torch
    from gliclass import GLiClassModel, ZeroShotClassificationPipeline
    from transformers import AutoTokenizer

    where = device() or ("cuda:0" if torch.cuda.is_available() else "cpu")
    model = GLiClassModel.from_pretrained(GLICLASS_MODEL)
    tokenizer = AutoTokenizer.from_pretrained(GLICLASS_MODEL, add_prefix_space=True)
    return ZeroShotClassificationPipeline(
        model,
        tokenizer,
        classification_type="multi-label",  # every option's score, not only the best one's
        device=where,
        max_length=GLICLASS_MAX_TOKENS,
        max_classes=128,  # the most options any rules offer is 84
        progress_bar=False,
    )


class GLiClassPlayer(Player):
    """GLiClass, an open-weight zero-shot classifier that scores every option in one pass.

    The state is the text to classify, the question its task prompt, and the option texts its
    labels. Each option gets its own score from 0 to 1; they are scaled to add up to 1 to serve
    as probabilities. Sees only the request.
    """

    name: ClassVar[str] = "gliclass"

    def __init__(self, pipeline: Any = None) -> None:
        self._pipeline = pipeline  # for tests; otherwise the shared model

    def choose(self, turn: Turn) -> Choice:
        request = turn.request
        pipeline = self._pipeline or shared("gliclass", load_gliclass)
        labels = [option.text for option in request.options]
        with _running:
            started = time.perf_counter()
            scored = pipeline(request.state, labels, threshold=0.0, prompt=request.question)[0]
            seconds = time.perf_counter() - started
        ids = {option.text: option.id for option in request.options}
        scores = {ids[s["label"]]: float(s["score"]) for s in scored if s["label"] in ids}
        total = sum(scores.values())
        best = max(scores, key=scores.__getitem__) if scores else None
        return answer_choice(
            request,
            best,
            {id: score / total for id, score in scores.items()} if total else {},
            model=GLICLASS_MODEL,
            seconds=seconds,
        )

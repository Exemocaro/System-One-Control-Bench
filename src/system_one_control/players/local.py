"""Decision models that run on this machine: free, but they need `uv sync --extra local`.

Each model is loaded once per process, the first time a game asks it anything, and every game
shares it. Only one answer is worked out at a time: the model already uses every core, or the
GPU, so games side by side would only wait for each other.
"""

from __future__ import annotations

import copy
import threading
import time
from collections.abc import Callable, Collection, Sequence
from typing import Any

from system_one_control.players import Choice, Player, Turn, answer_choice
from system_one_control.players.remote import llm_messages, setting
from system_one_control.prompts import Request

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
    return setting(DEVICE_NAME)


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


def laya_inputs(request: Request, tok: Callable[..., Any]) -> tuple[str, dict[str, Any], int, int]:
    """What Laya is asked: the state, its question with the options' texts, and the budgets."""
    max_len, head_max_len = laya_budget(
        lambda text: len(tok(text, add_special_tokens=False)["input_ids"]), request
    )
    question = {
        "type": "choice",
        "instructions": request.question,
        "criteria": [option.text for option in request.options],
    }
    return request.state, {"move": question}, max_len, head_max_len


class LayaPlayer(Player):
    """Laya's typed-decisions checkpoint, an open-weight model built to answer as Jev does.

    It is asked Jev's question, but with the options as a list of their texts: Laya would
    write each option's id in front of its text, and the ids mean nothing, while an option
    gets only 48 tokens. Sees only the request.
    """

    def __init__(self, laya: Any = None) -> None:
        self._laya = laya  # for tests; otherwise the shared model

    def choose(self, turn: Turn) -> Choice:
        request = turn.request
        agent = self._laya or shared("laya", load_laya)
        state, questions, max_len, head_max_len = laya_inputs(request, agent.tok)
        with _running:
            started = time.perf_counter()
            result = agent.system_one(state, questions, max_len=max_len, head_max_len=head_max_len)
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


def gliclass_inputs(request: Request) -> tuple[str, list[str], float, str]:
    """What GLiClass is asked: the text to classify, its labels, the threshold and the prompt."""
    labels = [option.text for option in request.options]
    return request.state, labels, 0.0, request.question


class GLiClassPlayer(Player):
    """GLiClass, an open-weight zero-shot classifier that scores every option in one pass.

    The state is the text to classify, the question its task prompt, and the option texts its
    labels. Each option gets its own score from 0 to 1; they are scaled to add up to 1 to serve
    as probabilities. Sees only the request.
    """

    def __init__(self, pipeline: Any = None) -> None:
        self._pipeline = pipeline  # for tests; otherwise the shared model

    def choose(self, turn: Turn) -> Choice:
        request = turn.request
        pipeline = self._pipeline or shared("gliclass", load_gliclass)
        text, labels, threshold, prompt = gliclass_inputs(request)
        with _running:
            started = time.perf_counter()
            scored = pipeline(text, labels, threshold=threshold, prompt=prompt)[0]
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


# Open-weight chat models run here, by short name: each is asked what the OpenRouter models are
# asked, but writes nothing; the probability it gives each option's id is read off instead (plan
# §15: "a local autoregressive LLM used only to score option IDs after prefill"). Another is a
# line here, for any model whose tokenizer writes each digit as a token of its own.
LOCAL_LLM_MODELS = {
    "qwen3.5-4b": "Qwen/Qwen3.5-4B",
}
# What the model is taken to have written so far: the start of the JSON answer that the
# OpenRouter models are held to, up to the option's number.
ANSWER_PREFIX = '{"option": "option_'


def number_probabilities(
    numbers: Collection[str], next_digits: Callable[[str], Sequence[float]]
) -> dict[str, float]:
    """The probability of each number, as a model writes it a digit at a time, among these.

    `next_digits(written)` is the model's probability of each digit 0 to 9 coming next once it
    has written `written`; the rest of its probability goes to ending the number there. At each
    point the probability is shared among the digits, or the end, that can still make one of
    `numbers`, as when a model's answer is held to them; so a number no other extends, such as
    84 out of 1 to 84, needs no call once its first digits are written.
    """
    found: dict[str, float] = {}

    def walk(written: str, share: float) -> None:
        onward = sorted(
            {n[len(written)] for n in numbers if n.startswith(written) and n != written}
        )
        if not onward:
            found[written] = share
            return
        digits = next_digits(written)
        weights = {digit: digits[int(digit)] for digit in onward}
        if written in numbers:
            weights[""] = max(0.0, 1 - sum(digits))
        total = sum(weights.values())
        for digit, weight in weights.items():
            part = share * (weight / total if total else 1 / len(weights))
            if digit:
                walk(written + digit, part)
            else:
                found[written] = part

    walk("", 1.0)
    return found


class LocalLLM:
    """A causal language model and its tokenizer, loaded here, that reads off digit odds."""

    def __init__(self, repo: str) -> None:
        # Optional dependencies: uv sync --extra local
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.where = device() or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(repo)
        model = AutoModelForCausalLM.from_pretrained(repo, dtype=torch.bfloat16)
        self.model = model.to(self.where).eval()
        self.digits = [self.tokenizer.convert_tokens_to_ids(str(d)) for d in range(10)]
        written = self.tokenizer(ANSWER_PREFIX + "12", add_special_tokens=False)["input_ids"]
        if written[-2:] != self.digits[1:3]:
            raise ValueError(f"{repo} does not write each digit as a token of its own")

    def prompt(self, request: Request) -> list[int]:
        """The chat, as the model's own template lays it out, then the start of the answer."""
        text = self.tokenizer.apply_chat_template(
            llm_messages(request),
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,  # templates without thinking ignore it
        )
        ids: list[int] = self.tokenizer(text + ANSWER_PREFIX, add_special_tokens=False)["input_ids"]
        return ids

    def option_probabilities(self, request: Request, prompt: Sequence[int]) -> dict[str, float]:
        """The probability of each option id, read after one pass over the prompt."""
        torch = self.torch
        with torch.inference_mode():
            ids = torch.tensor([list(prompt)], device=self.where)
            out = self.model(ids, use_cache=True, logits_to_keep=1)  # the last position only
            first, cache = out.logits[0, -1], out.past_key_values

            def next_digits(written: str) -> list[float]:
                logits = first
                if written:  # a copy of the cache, since each digit tried moves it on
                    digits = [[self.digits[int(d)]] for d in written]
                    step = torch.tensor(digits, device=self.where).T
                    later = self.model(step, past_key_values=copy.deepcopy(cache), use_cache=True)
                    logits = later.logits[0, -1]
                probabilities = logits.float().softmax(-1)[self.digits]
                return [float(p) for p in probabilities]

            numbers = {option.id.removeprefix("option_") for option in request.options}
            found = number_probabilities(numbers, next_digits)
        return {f"option_{number}": p for number, p in found.items()}


class LocalLLMPlayer(Player):
    """An open-weight chat model on this machine, asked as the OpenRouter models are.

    It writes nothing and so cannot reason: the options' probabilities are read from one pass
    over the chat, and the likeliest is played. Sees only the request.
    """

    def __init__(self, repo: str, model: Any = None) -> None:
        self.repo = repo
        self._model = model  # for tests; otherwise the shared model

    def choose(self, turn: Turn) -> Choice:
        request = turn.request
        model = self._model or shared(self.repo, lambda: LocalLLM(self.repo))
        with _running:
            started = time.perf_counter()
            prompt = model.prompt(request)
            probabilities = model.option_probabilities(request, prompt)
            seconds = time.perf_counter() - started
        best = max(probabilities, key=probabilities.__getitem__) if probabilities else None
        return answer_choice(
            request,
            best,
            probabilities,
            input_tokens=len(prompt),
            model=self.repo,
            seconds=seconds,
        )

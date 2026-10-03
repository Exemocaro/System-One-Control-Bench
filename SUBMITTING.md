# Submitting to the leaderboard

The core track is compass rules, conditions `map` and `everything`, all 100 puzzles:
200 games, up to ~3,400 paid calls worst case (one per move).

## Run it

Built-in players need nothing: `uv run socb benchmark --track core --players jev --allow-paid`.
A chat model on any OpenAI-compatible endpoint goes in `players.toml` (read with
`--players-file`, or `./players.toml` if present):

```toml
[players.my-chat-model]
kind = "chat"
base_url = "https://api.example.com/v1"
model = "my-model-1"
api_key_env = "MY_API_KEY"
```

then `uv run socb benchmark --track core --players my-chat-model --allow-paid`.
A bounded decision model serves `POST /decide` with
`{"state": ..., "question": ..., "options": [{"id": ..., "text": ...}]}` and answers
`{"probabilities": {id: p}}` or `{"choice": id}` (see
`leaderboard/decision_server_example.py`); a server on your own machine costs nothing,
so say `paid = false`:

```toml
[players.my-decision-model]
kind = "decision"
url = "http://localhost:8000/decide"
paid = false
```

then benchmark it the same way (still pass `--allow-paid` unless `paid = false`).

## Submit it

`uv run socb submit benchmarks/<file>.jsonl --kind chat --name MyModel --org MyOrg --url https://example.com
--notes "what it is"` validates the file first (every game replayed: options, best moves,
won/closest, probabilities, full core coverage) and writes `leaderboard/entries/<player>.json`
with the entry plus the player's core games in `leaderboard/results/<player>.jsonl`.
`--kind` (bounded decision, chat, local or baseline) is required except for the four
baselines; a file with several players needs `--player` to pick one.
Then `uv run socb leaderboard` and commit its outputs (`entries/`, `README.md`, `docs/index.html`).
Open a pull request; CI revalidates and rebuilds, failing on any diff.

Validation proves the games are consistent, not that your model made the choices: anyone can
submit solver play under another name, and cost and latency are self-reported and unchecked.
Runs may be re-run on request. The puzzles and examples are frozen: any change to them means
benchmark version 1.1, and older results no longer validate.

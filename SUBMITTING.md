# Submitting to the leaderboard

The core track is compass rules, conditions `map` and `everything`, all 100 puzzles:
200 games, up to ~3,400 paid calls worst case (one per move).

## Run it

Built-in players need nothing: `uv run socb benchmark --track core --players jev --allow-paid`.
A chat model on any OpenAI-compatible endpoint goes in `players.toml`:

```toml
[players.my-chat-model]
kind = "chat"
base_url = "https://api.example.com/v1"
model = "my-model-1"
api_key_env = "MY_API_KEY"
```

then `uv run socb benchmark --track core --players my-chat-model --allow-paid`.
A bounded decision model serves `POST /decide` with
`{"state": ..., "question": ..., "options": [{"id": ..., "text": ...}]` and answers
`{"probabilities": {id: p}}` or `{"choice": id}` (see
`leaderboard/decision_server_example.py`):

```toml
[players.my-decision-model]
kind = "decision"
url = "http://localhost:8000/decide"
```

then benchmark it the same way.

## Submit it

`uv run socb submit benchmarks/<file>.jsonl --name MyModel --org MyOrg --url https://example.com
--notes "what it is"` validates the file first (every game replayed: options, best moves,
won/closest, probabilities, full core coverage) and writes `leaderboard/entries/<player>.json`.
Open a pull request with the entry and the results file; CI revalidates and rebuilds the
table, failing if the committed files differ from the rebuild.

Validation proves the games are consistent, not that your model made the choices; runs may
be re-run on request.

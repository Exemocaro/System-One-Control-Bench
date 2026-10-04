# Submitting to the leaderboard

The core track is compass rules, conditions `map` and `everything` (the full context), all
100 puzzles: 200 games, up to ~3,400 paid calls worst case (one per move, not counting
retries). Any player can be
submitted: a chat model, a decision endpoint, or a Python `Player` from the README, since
`socb submit` works from the results file, not from how the player runs.
The repository is <https://github.com/Exemocaro/JevStuff>; submissions are pull requests to it.

## Run it

Built-in players need no `players.toml` entry (paid ones still need their key in `.env`):
`uv run socb benchmark --track core --players jev --allow-paid`.
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

The keys of a `players.toml` entry:

| Key | Needed for | Meaning |
| --- | --- | --- |
| `kind` | all | `chat` or `decision` |
| `base_url`, `model` | `chat` | the endpoint (`/chat/completions` is appended) and model name |
| `url` | `decision` | the endpoint that answers `POST` |
| `api_key_env` | optional | name of the environment variable (or `.env` entry) holding the API key |
| `paid` | optional, default `true` | `false` for a free player, so `--allow-paid` is not required |
| `reasoning` | optional, `chat` only, default `false` | let the model reason first, capped at 1,024 tokens |

A `chat` endpoint should support JSON-schema structured output: every request sends a strict
`response_format` that allows only one option id as the answer. An endpoint that rejects it
fails every game as an error; one that ignores it is read for the last valid option id in the
reply, and a reply with none is an error.

A decision model serves `POST /decide` with
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

then `uv run socb benchmark --track core --players my-decision-model` (no `--allow-paid`,
since `paid = false`).

Probabilities are keyed by option id and are not renormalised; ids that are not options are
dropped from the record. The likeliest id is played (a tie goes to the first id in sorted
order). An answer whose id is not an option, or with neither field, ends the game as an
error, which counts as lost.

## Submit it

`uv run socb submit benchmarks/<file>.jsonl --kind chat --name MyModel --org MyOrg --url https://example.com
--notes "what it is"` (`--org` and `--url` are optional) validates the file first (every game replayed: options, best moves,
won/closest, probabilities, full core coverage) and writes `leaderboard/entries/<player>.json`
with the entry plus the player's core games in `leaderboard/results/<player>.jsonl`.
`--kind` (`baseline`, `chat` or `decision`: the type of model, not where it runs) is required
except for the four baselines; a file with several players needs `--player` to pick one.
Then `uv run socb leaderboard` and commit `leaderboard/results/<player>.jsonl`, the entry in
`leaderboard/entries/`, and the rebuilt `leaderboard/README.md` and `docs/index.html`.
Open a pull request; CI revalidates and rebuilds, failing on any diff.

Submit one core-track run per entry, with the benchmark's requests unchanged, and say in
`--notes` anything model-specific (decoding, quantisation, reasoning settings).

Validation proves the games are consistent, not that your model made the choices: anyone can
submit solver play under another name, and cost and latency are self-reported and unchecked.
Runs may be re-run on request. The puzzles and examples are frozen: any change to them means
benchmark version 1.1 (the current version is 1.0). Results made on version 1.0 stay 1.0
results; they do not validate against the 1.1 puzzles.

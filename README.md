# System-One Control Bench

![CI](https://github.com/Exemocaro/JevStuff/actions/workflows/ci.yml/badge.svg)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue)
![uv](https://img.shields.io/badge/built%20with-uv-purple)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

> Can a non-generative decision model, one that picks an answer from a list instead of writing one, steer an agent across a small grid?

The player sees a grid as text and chooses the next move from a list of options. A breadth-first solver knows every best move, so each move is scored exactly. There are 100 puzzles, ten conditions that change what the player is told, and five rule sets (one step per move, or several steps chosen together). The puzzles are the final benchmark: there is no held-out set.

The main finding: with full context Jev picks a best move on 90% of the shared exam positions, yet wins 57 of 100 games. Good single decisions do not reliably add up to finished games. See the report, [paper/main.pdf](paper/main.pdf).

What a player sees (shortened):

```
Map:        You are A at (7, 1). Goal G at (1, 4); key K at (7, 2).
              0123456789        North of you is a wall. South of you is the key.
            1 #......A.#
            2 #..##..K.#
            3 #D....#..#
            4 #G#.#...##
Question:   Your next target is the key K at (7, 2). Which move is the first step of the shortest path to it?
Options:    option_1: move south (down): you move to (7, 2) and pick up the key
            option_2: move north (up): blocked, you stay at (7, 1)
            option_3: move west (left): you move to (6, 1)
            option_4: move east (right): you move to (8, 1)
```

`examples/<condition>.json` holds the exact request each condition sends.

## Quick start

Needs [uv](https://docs.astral.sh/uv/), which installs Python 3.11. Works on Windows, Linux and WSL2.

```bash
uv sync                      # install
uv run pytest                # tests
uv run socb benchmark        # the free players on all 100 puzzles, a few seconds
uv run socb exam             # the fixed-state exam: the 4 free baselines answer 495 positions, map only
uv run socb web              # board viewer at http://127.0.0.1:8000
```

To use Jev or the chat models, copy `.env.example` to `.env` and fill in `TYPESAFE_API_KEY` (Jev) and/or `OPENROUTER_API_KEY` (chat models). Those players cost money and are refused unless you add `--allow-paid`; the refusal says how many calls the run can make at most. Local models (Laya, GLiClass, Qwen3.5-4B) need `uv sync --extra local`, which installs PyTorch (several GB); a plain `uv sync` removes it again, so run them with `uv run --extra local`.

```bash
uv run --extra local socb benchmark --players laya               # a local model
uv run socb benchmark --players jev --allow-paid                 # Jev, map only: up to 1,690 calls, not counting retries
uv run socb benchmark --players jev --conditions all --allow-paid
uv run socb benchmark --levels 1-3 --rules two-moves --players random,solver   # sequence rules: the greedy players do compass only
uv run socb benchmark --track core --players jev --allow-paid     # the leaderboard track: compass, map and everything
```

Results go to `benchmarks/<date>_<time>_<what was run>.jsonl` (every move of every game) and a `.txt` score table. Cost, output files, resuming, local models and extending the code: [docs/details.md](docs/details.md).

## Scores

| Score | Meaning |
| --- | --- |
| `won` | the success rate: games that reached the goal before the move limit (twice the solver's moves) |
| `progress` | how far a game got toward the goal at its closest: 1 for a win, 0 for never getting nearer than the start |
| `SPL` | fewest moves over moves used for a won game, 0 for a lost one |
| `errors` | games ended because the player failed to answer (they count as lost; should be 0) |

## Results

Compass rules, 100 puzzles, wins out of 100 / mean progress. The baselines do not read the request, so every condition gives them the same games. Results files are in `benchmarks/`.

| Player | `map` (map only) | `everything` (full context) |
| --- | --- | --- |
| Random | 4 / 0.25 | same |
| Greedy | 28 / 0.36 | same |
| Greedy (walls) | 37 / 0.47 | same |
| Solver | 100 / 1.00 | same |
| Jev | 32 / 0.43 | 57 / 0.68 |
| Laya | 2 / 0.10 | 12 / 0.26 |
| GLiClass | 3 / 0.10 | 13 / 0.22 |
| Gemma 4 26B | 35 / 0.45 | 61 / 0.71 |
| DeepSeek V4.1 Flash | 39 / 0.55 | 60 / 0.72 |
| DeepSeek V4.1 Flash (reasoning) | 67 / 0.79 | 80 / 0.86 |
| Qwen3.5-4B | 14 / 0.34 | 45 / 0.66 |

## Conditions

Every condition includes the **map**: the rules, the numbered map, your position, what you carry, where the objects are. Four components can be added, each something code works out for the player.

| Condition | surroundings | memory | lookahead | subgoal |
| --- | :---: | :---: | :---: | :---: |
| `map` | | | | |
| `map+surroundings` | ✓ | | | |
| `map+memory` | | ✓ | | |
| `map+lookahead` | | | ✓ | |
| `map+subgoal` | | | | ✓ |
| `everything` (the full context) | ✓ | ✓ | ✓ | ✓ |
| `everything-surroundings` | | ✓ | ✓ | ✓ |
| `everything-memory` | ✓ | | ✓ | ✓ |
| `everything-lookahead` | ✓ | ✓ | | ✓ |
| `everything-subgoal` | ✓ | ✓ | ✓ | |

`surroundings`: what is next to you, and where the key, door and goal are. `memory`: the moves so far (the report calls it *move history*). `lookahead`: what each option would do (*move outcomes* in the report). `subgoal`: the question names the next target.

## Rules

| Rules | A move is | Options |
| --- | --- | :---: |
| `compass` | one step | 4 |
| `two-moves` | two steps chosen together | 16 |
| `three-moves` | three steps chosen together | 64 |
| `up-to-two-moves` | one or two steps | 20 |
| `up-to-three-moves` | one, two or three steps | 84 |

Choose with `--rules`. Every sequence is offered, blocked or not. A blocked step is wasted; reaching the goal ends the move.

## Players

`random`, `greedy`, `greedy-walls` and `solver` are free baselines. `jev` (`jev-1.13.0`) is paid. `laya`, `gliclass` and `qwen3.5-4b` run on your machine. `gemma-4-26b` and `deepseek-v4.1-flash` (and the same with `-think`, which lets the model reason first, capped at 1,024 tokens) are paid, through OpenRouter.

A chat model on any OpenAI-compatible endpoint, or a decision endpoint, is added with an entry in `players.toml`, no code needed: see [SUBMITTING.md](SUBMITTING.md). To add a player written in Python, subclass `Player` and register it:

```python
from system_one_control.players import PLAYERS, Choice, Player, PlayerEntry, Turn


class FirstOption(Player):
    def choose(self, turn: Turn) -> Choice:
        return Choice(turn.request.options[0].move)  # read turn.request only, never turn.board


PLAYERS["first"] = PlayerEntry(FirstOption)  # paid=True for a player that costs money
```

In the repository, that line goes in `src/system_one_control/players/__init__.py`; then `uv run socb benchmark --players first` plays it. A chat model on OpenRouter needs only a line in `LLM_MODELS` in `players/remote.py`. More in [docs/details.md](docs/details.md).

## Puzzles

Puzzles are YAML files under `puzzles/`: 100 over the levels 1, 2, 3, 4, 5, 6, 8, 10, 12, 15 and 20, where the level is the solver's distance to the goal. `#` wall, `.` floor, `A` agent, `G` goal, `K` key, `D` locked door. `uv run socb generate` tops each level up with generated puzzles checked by the solver.

## Analysis

`analysis/` recomputes every table and figure of the paper from the results files, with no API calls: `uv run --with matplotlib python analysis/analyze.py`. See `analysis/README.md` for the definitions.

## Leaderboard

The core track is compass rules, `map` and `everything`, all 100 puzzles: 200 games per player, so models can be compared without paying for all 5,000 games. The table is [leaderboard/README.md](leaderboard/README.md); the same results as a web page are at [exemocaro.github.io/JevStuff](https://exemocaro.github.io/JevStuff/), built from `docs/index.html`. To add a model, any chat model, decision endpoint or Python `Player`, follow [SUBMITTING.md](SUBMITTING.md).

## Citation

Report: *Evaluating Non-Generative Decision Models in Sequential Gridworld Tasks* (`paper/`). Cite it with `CITATION.cff`.

## License

MIT; see `LICENSE`.

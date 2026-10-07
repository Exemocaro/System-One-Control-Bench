# System-One Control Bench

![CI](https://github.com/Exemocaro/System-One-Control-Bench/actions/workflows/ci.yml/badge.svg)
![Python 3.11](https://img.shields.io/badge/python-3.11-blue)
![uv](https://img.shields.io/badge/built%20with-uv-purple)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

> Can a non-generative decision model, one that picks an answer from a list instead of writing one, steer an agent across a small grid?

The player sees a small grid puzzle as text and chooses the agent's next move from a list of options: reach the goal, avoid walls, and collect a key when a locked door blocks the way. A breadth-first solver knows the shortest route from every position, so each move is scored exactly: it either starts a shortest route (an optimal move) or it does not. There are 100 puzzles, ten conditions that change what the player is told, and five rule sets (one step per move, or several steps chosen together). The puzzles are the final benchmark: there is no held-out set.

The main finding: with full context, Jev chooses an optimal move in about 90% of the positions of the exam, where every model answers the same fixed situations, yet it finishes only 57 of the 100 puzzles when it plays whole games. Strong single decisions do not guarantee a finished game. Read the report, [paper/main.pdf](paper/main.pdf), or browse the results and two recorded games on the [website, socb.dev](https://socb.dev).

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
| `won` | games won, the success rate: games finished within the move limit, which is twice the shortest route |
| `progress` | how much closer the agent got to the goal at its best point: 1 means finished, 0 means it never got closer than where it started |
| `SPL` | for a won game, the moves of the shortest route over the moves used; 0 for a lost one |
| `errors` | games ended because the player failed to answer (they count as lost; should be 0) |

## Results

Compass rules (one step per move), 100 puzzles: games won out of 100 / mean progress, sorted by full-context games won. The programmed baselines do not read the request, so both conditions give them the same games. Results files are in `benchmarks/`.

| Player | Full context (`everything`) | Map only (`map`) |
| --- | --- | --- |
| DeepSeek V4.1 Flash (reasoning) | 80 / 0.86 | 67 / 0.79 |
| Gemma 4 26B | 61 / 0.71 | 35 / 0.45 |
| DeepSeek V4.1 Flash | 60 / 0.72 | 39 / 0.55 |
| Jev | 57 / 0.68 | 32 / 0.43 |
| Qwen3.5-4B | 45 / 0.66 | 14 / 0.34 |
| GLiClass | 13 / 0.22 | 3 / 0.10 |
| Laya | 12 / 0.26 | 2 / 0.10 |
| *Programmed baselines* | | |
| Solver | 100 / 1.00 | same |
| Greedy (walls) | 37 / 0.47 | same |
| Greedy | 28 / 0.36 | same |
| Random | 4 / 0.25 | same |

## Conditions

Every condition includes the **map**: the rules, the numbered map, the agent's position, whether it carries the key, and where the objects are. Four components can be added, each worked out by code for the player, so the results measure the model together with the information it receives.

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

`surroundings`: what is next to the agent, and how far away the key, door and goal are. `memory` (*move history* in the report and on the website): every move already made, and what it did. `lookahead` (*move outcomes*): what would happen if the player chose each option. `subgoal`: the question names the object to aim for next, the key, the door or the goal.

## Rules

| Rules | A move is | Options |
| --- | --- | :---: |
| `compass` | one step | 4 |
| `two-moves` | two steps chosen together | 16 |
| `three-moves` | three steps chosen together | 64 |
| `up-to-two-moves` | one or two steps | 20 |
| `up-to-three-moves` | one, two or three steps | 84 |

Choose with `--rules`. Under the sequence rules the player commits to a whole sequence before seeing the new situation. Every sequence is offered, blocked or not: a blocked step is wasted, the remaining steps still run, and reaching the goal ends the move.

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

The core track is compass rules, `map` and `everything`, all 100 puzzles: 200 games per player, so models can be compared without paying for all 5,000 games. The table is [leaderboard/README.md](leaderboard/README.md); the same results as a web page, with two recorded games to step through, are at [socb.dev](https://socb.dev), built from `docs/index.html` by `uv run socb leaderboard`. To add a model, any chat model, decision endpoint or Python `Player`, follow [SUBMITTING.md](SUBMITTING.md).

## Citation

Report: *Evaluating Non-Generative Decision Models in Sequential Gridworld Tasks* (`paper/`). Cite it with `CITATION.cff`.

## License

MIT; see `LICENSE`.

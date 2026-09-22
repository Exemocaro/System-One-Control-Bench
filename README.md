# System-One Control Bench

Can a bounded decision model — one that picks an answer from a list rather than writing one, like [Jev](https://docs.typesafe.ai/introduction) — steer an agent across a small grid to a goal?

Each scenario is a tiny map. At every move the player is shown the board as text, asked which way to go, and given the allowed moves as options. A breadth-first solver knows the best moves, so every choice can be scored, and a random player shows what chance looks like.

## Setup

Windows, Linux or WSL2, with [uv](https://docs.astral.sh/uv/), which installs Python 3.11 itself.

```bash
uv sync
uv run pytest
```

Jev reads its key from `TYPESAFE_API_KEY` or `JEV_API_KEY`, in the environment or in a gitignored `.env` file (copy `.env.example`).

## Use

```bash
uv run socb web                                   # the board viewer, at http://127.0.0.1:8000
uv run socb experiment                            # solver and random on every puzzle, full prompt
uv run socb experiment --players jev --first-move-only --allow-paid
uv run socb generate                              # top every level up to 10 puzzles
```

In the viewer, pick a scenario, a player and a prompt, then play one move at a time or play to the end. **Next puzzle** moves down the list. Beside the board is exactly what the player was shown, with the probability it gave each option.

An experiment prints how many first moves each player got right, grouped by level, and saves one line per game to `results/latest.jsonl`. It uses the `full` prompt unless `--prompts` says otherwise. A paid player is refused without `--allow-paid`, and the refusal says the most calls the run could make: one per move.

The options are shuffled for every move, with a seed made from the scenario and the move number, so a run is repeatable but no direction always sits first.

## How it fits together

| File | What it is |
| --- | --- |
| `board.py` | `Board`: the map, where the agent stands, and what it carries |
| `rules.py` | `Rules`: the allowed moves and what each does. `CompassRules` moves north, south, east and west |
| `solver.py` | `Solver`: the fewest moves to the goal, and every move that starts such a path |
| `scenario.py` | `Scenario`: a board, its rules and how far the goal is, loaded from `scenarios/level-NN/*.yaml`, where the level is the number of moves to the goal |
| `prompt.py` | `Prompt`: a wording, loaded from `prompts/*.yaml`, that turns a board into the text a player sees |
| `players.py` | `Player`: anything that picks a move. `RandomPlayer`, `SolverPlayer`, and `JevPlayer` in `jev.py` |
| `game.py` | `Game`: one player on one scenario, a `Step` per move |
| `experiment.py` | every scenario × prompt × player, summarized and saved |
| `generator.py` | `PuzzleGenerator`: random rooms and mazes at an exact level, checked by the solver |
| `web/` | the FastAPI viewer |

**A scenario** is a YAML file in the folder for its level, such as `scenarios/level-03/key-first.yaml`. Every level from 1 to 10 has 10: the hand-made ones, topped up by `socb generate` with random rooms and mazes named `gen-*.yaml`. Generating again with a new `--seed` replaces only the generated ones. From level 3 up, every puzzle needs the key. The tests check that the solver agrees with each file's stated distance. A game ends once it has used twice the moves the solver needs:

```yaml
description: The door is ahead of the key, so you have to step north for the key first.
moves_to_goal: 3
map: |
  #####
  #KDG#
  #A###
  #####
```

`#` wall, `.` floor, `A` agent, `G` goal, `K` key, `D` locked door. Walking onto the key picks it up; walking into the door while carrying it opens the door and steps through.

**A prompt** is a YAML file whose templates are filled from the board. `full` is the baseline; each `full-*` wording adds one thing to it, and `everything` adds them all:

| Prompt | Adds to `full` |
| --- | --- |
| `full-grid` | column and row numbers around the map |
| `full-around` | what is next to you in each direction, and where the key, door and goal are relative to you |
| `full-history` | every move so far and what it did, so a blocked move doesn't produce the identical prompt again |
| `full-outcomes` | what each option would do. Code looks one move ahead for the player, so this is a different condition, not just a wording |

The placeholders are `{rules}`, `{map}`, `{map_grid}`, `{legend}`, `{position}`, `{holding}`, `{objects}`, `{moves}` and `{history}`, plus what the rules add through `Rules.facts()`; `CompassRules` adds `{around}` and `{relative}`. `show_outcomes: true` appends each move's result to its option, and `options:` renames moves:

```yaml
description: Full, plus every move so far and what it did.
state: |
  {rules}

  Map, where coordinates are (column, row) counted from 0 at the top left ({legend}):
  {map}

  You are A at {position}. {holding}
  Objects: {objects}.

  {history}
question: Which move gets you to the goal G in the fewest moves?
```

**A new player** subclasses `Player`, implements `choose(turn) -> Choice`, and is added to `PLAYERS` in `players.py`. A model player must read only `turn.request` — the text it is shown — never `turn.board`.

**New rules** — MiniGrid's turn-and-step movement, say — subclass `Rules` and implement `moves`, `apply` and `is_won`. Scenarios select them with `rules: <name>`, and prompts adapt automatically, because the options come from the rules' moves and extra placeholders from `Rules.facts()`.

## License

Not yet chosen.

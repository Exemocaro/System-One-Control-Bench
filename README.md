# System-One Control Bench

Can a bounded decision model — one that picks an answer from a list rather than writing one, like [Jev](https://docs.typesafe.ai/introduction) — steer an agent across a small grid to a goal?

Each scenario is a tiny map. At every move the player is shown the board as text, asked which way to go, and given the allowed moves as options. A breadth-first solver knows the best moves, so every choice can be scored, and a random player shows what chance looks like.

## Setup

Linux or WSL2, Python 3.11 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra models    # --extra models adds Jev
uv run pytest
```

Jev reads its key from `TYPESAFE_API_KEY` or `JEV_API_KEY`, in the environment or in a gitignored `.env` file (copy `.env.example`).

## Use

```bash
uv run socb web                                   # the board viewer, at http://127.0.0.1:8000
uv run socb experiment                            # solver and random on every scenario and prompt
uv run socb experiment --players jev --first-move-only --allow-paid
```

In the viewer, pick a scenario, a player and a prompt, then play one move at a time or play to the end. Beside the board is exactly what the player was shown, with the probability it gave each option.

An experiment prints how many first moves each player got right, grouped by distance to the goal, and saves one line per game to `results/latest.jsonl`. A paid player is refused without `--allow-paid`, and the refusal says the most calls the run could make: one per move.

## How it fits together

| File | What it is |
| --- | --- |
| `board.py` | `Board`: the map, where the agent stands, and what it carries |
| `rules.py` | `Rules`: the allowed moves and what each does. `CompassRules` moves north, south, east and west |
| `solver.py` | `Solver`: the fewest moves to the goal, and every move that starts such a path |
| `scenario.py` | `Scenario`: a board, its rules and its known answer, loaded from `scenarios/*.yaml` |
| `prompt.py` | `Prompt`: a wording, loaded from `prompts/*.yaml`, that turns a board into the text a player sees |
| `players.py` | `Player`: anything that picks a move. `RandomPlayer`, `SolverPlayer`, and `JevPlayer` in `jev.py` |
| `game.py` | `Game`: one player on one scenario, a `Step` per move |
| `experiment.py` | every scenario × prompt × player, summarized and saved |
| `web/` | the FastAPI viewer |

**A scenario** is a YAML file. The tests check that the solver agrees with its stated distance and best first moves:

```yaml
description: The door is ahead of the key, so you have to step north for the key first.
moves_to_goal: 3
best_first_moves: [north]
map: |
  #####
  #KDG#
  #A###
  #####
```

`#` wall, `.` floor, `A` agent, `G` goal, `K` key, `D` locked door. Walking onto the key picks it up; walking into the door while carrying it opens the door and steps through.

**A prompt** is a YAML file whose templates are filled from the board. The placeholders are `{rules}`, `{map}`, `{legend}`, `{position}`, `{holding}`, `{objects}` and `{moves}`, plus anything the rules add through `Rules.facts()`. `options:` optionally renames the moves:

```yaml
description: Like map-only, but the moves are called up, down, left and right.
state: |
  {map}

  {legend}. {holding}
question: Which way should A move to reach G?
options: {north: up, south: down, east: right, west: left}
```

**A new player** subclasses `Player`, implements `choose(turn) -> Choice`, and is added to `PLAYERS` in `players.py`. A model player must read only `turn.request` — the text it is shown — never `turn.board`.

**New rules** — MiniGrid's turn-and-step movement, say — subclass `Rules` and implement `moves`, `apply` and `is_won`. Scenarios select them with `rules: <name>`, and prompts adapt automatically, because the options come from the rules' moves and extra placeholders from `Rules.facts()`.

## License

Not yet chosen.

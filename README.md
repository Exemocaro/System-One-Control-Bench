# System-One Control Bench

Can a bounded decision model — one that picks an answer from a list rather than writing one, like [Jev](https://docs.typesafe.ai/introduction) — steer an agent across a small grid to a goal?

Each scenario is a tiny map. At every move the player is shown the board as text, asked which way to go, and given the allowed moves as options. A breadth-first solver knows the best moves, so every choice can be scored. Three simple players mark what a model has to beat: one picks at random, and two greedy ones walk straight at the next target, the second never bumping into a wall.

## Setup

Windows, Linux or WSL2, with [uv](https://docs.astral.sh/uv/), which installs Python 3.11 itself.

```bash
uv sync
uv run pytest
uv run pre-commit install    # lint, format, type-check on commit; tests on push
```

Jev reads its key from `TYPESAFE_API_KEY` or `JEV_API_KEY`, in the environment or in a gitignored `.env` file (copy `.env.example`).

## Use

```bash
uv run socb web                                   # the board viewer, at http://127.0.0.1:8000
uv run socb benchmark                             # the free players on every puzzle, map condition
uv run socb benchmark --players jev --allow-paid  # Jev on every puzzle, 8 games at a time
uv run socb benchmark --players jev --conditions all --first-move-only --allow-paid
uv run socb generate                              # top every level up to 10 puzzles
```

In the viewer, pick a scenario, a player and a condition, then play one move at a time or play to the end. **Next puzzle** moves down the list. Beside the board is exactly what the player was shown, with the probability it gave each option.

A benchmark plays every game to the end, as the viewer's play-to-the-end button does, several games at once (`--workers`, 8 by default). It prints, for each player and condition, the games it won at each level and three scores over all its games, with the best of each in bold, leaving out the solver:

| Score | What it is |
| --- | --- |
| `won` | games that reached the goal before running out of moves |
| `optimal` | the share of all moves that started a shortest path from where the player stood |
| `SPL` | success weighted by path length: a won game scores the fewest moves over the moves used, a lost one 0 |
| `errors` | games that ended because the player failed to answer, such as a failed API call. They count as lost, so check this is 0 |

With `--first-move-only`, each level counts the optimal first moves instead, and won and SPL, which mean nothing after one move, are left out.

The rows run from worst to best of the simple players, random, greedy, greedy with walls, then the solver, and any other player below them. For a paid player it also prints the calls made and the input tokens billed (Jev does not charge for output tokens).

A benchmark is saved to the `benchmarks/` folder, which is kept in git, as `<date>_<players>_<conditions>.jsonl`, with the scenarios and `first-move` added when they were chosen, and one line per game listing every move (the options in the order shown, the move chosen, the probability the player gave each move, the best moves and the tokens billed), and beside it the table as `.txt`. A run never overwrites an earlier file. It uses the `map` condition unless `--conditions` says otherwise. A paid player is refused without `--allow-paid`, and the refusal says the most calls the run could make: one per move.

The options are shuffled for every move, with a seed made from the scenario and the move number, so a run is repeatable but no direction always sits first.

## How it fits together

| File | What it is |
| --- | --- |
| `board.py` | `Board`: the map, where the agent stands, and what it carries |
| `rules.py` | `Rules`: the allowed moves, what each does, and how to describe it. `CompassRules` moves north, south, east and west |
| `solver.py` | `Solver`: the fewest moves to the goal, and every move that starts such a path |
| `scenario.py` | `Scenario`: a board, its rules and how far the goal is, loaded from `scenarios/level-NN/*.yaml`, where the level is the number of moves to the goal |
| `request.py` | `Request`: exactly what a player is shown, the state, the question and the options |
| `conditions.py` | `Condition`: which ingredients a player gets, and `CONDITIONS`, the ablation |
| `examples.py` | writes what each condition shows the player to `examples/` |
| `players.py` | `Player`: anything that picks a move. `RandomPlayer`, `GreedyPlayer`, `WallAwareGreedyPlayer`, `SolverPlayer`, `ScriptedPlayer`, and `JevPlayer` in `jev.py` |
| `game.py` | `Game`: one player on one scenario, a `Step` per move |
| `benchmark.py` | every scenario × condition × player, played side by side, summarized and saved |
| `generator.py` | `PuzzleGenerator`: random rooms and mazes at an exact level, checked by the solver |
| `web/` | the FastAPI viewer |

**A scenario** is a YAML file in the folder for its level, such as `scenarios/level-03/key-first.yaml`. Every level from 1 to 10 has 10: the hand-made ones, topped up by `socb generate` with random rooms and mazes named `gen-*.yaml`. Generating again with a new `--seed` replaces only the generated ones. From level 3 up, every generated puzzle needs the key, except the keyless ones at level 4 below. The tests check that the solver agrees with each file's stated distance. A game ends once it has used three times the moves the solver needs.

From level 3 up, a growing share of puzzles is built so that walking straight at the target is not enough. `LEVEL_KINDS` in `generator.py` says how many of each kind a level gets, and hand-made puzzles count toward the kind they fit:

| Level | Puzzles |
| --- | --- |
| 1 and 2 | any |
| 3 | 1 that the wall-aware greedy player cannot win, the hand-made `nook` |
| 4 | 1 that it cannot win, without a key, since with one no wrong turn is possible this close to the goal |
| 5 and 6 | 2 that it cannot win, the rest it can |
| 7 | 3 that it cannot win, the rest it can |
| 8 and 9 | 5 that it cannot win, 5 that it can |
| 10 | none that it can win; 5 of them also have a second, longer route to the goal (walling off one shortest route leaves another, longer one) |

A scenario file:

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

**A condition** is what a player is told, and `CONDITIONS` in `conditions.py` lists the ablation. The baseline, `map`, gives the rules, the map with column and row numbers, your position, what you carry and where the objects are, and asks "What is the best next move?". Every other condition switches on **ingredients**, each one thing that code works out for the player:

| Ingredient | What the player gets |
| --- | --- |
| `surroundings` | what is next to you in each direction, and where the key, door and goal are relative to you |
| `memory` | every move so far and what it did, so a blocked move doesn't produce the identical prompt again |
| `lookahead` | each option says what that move would do. Code looks one move ahead for the player |
| `subgoal` | the question names the next thing to reach: the key, then the door, then the goal |

The conditions add each ingredient to the map alone (`map+surroundings`, `map+memory`, `map+lookahead`, `map+subgoal`), give all four at once (`everything`), and take each one away from that (`everything-surroundings`, `everything-memory`, …). The first set shows what an ingredient is worth on its own, the second whether it is still needed once the others are there. A new condition is one line:

```python
(Condition("map+memory+lookahead", memory=True, lookahead=True),)
```

**The `examples/` folder** holds, for every condition, exactly what the player is shown on `gen-10-01` after a move and a blocked move. It is the quickest way to read a condition. A test fails when the wording changes, and `uv run socb examples` rewrites the files, so every change of wording shows up in the diff.

**A new player** subclasses `Player`, implements `choose(turn) -> Choice`, and is added to `PLAYERS` in `players.py`. A model player must read only `turn.request` — the text it is shown — never `turn.board`.

**New rules** — MiniGrid's turn-and-step movement, say — subclass `Rules` and implement `moves`, `apply` and `is_won`. Scenarios select them with `rules: <name>`, and implement `describe_outcome`, `describe_surroundings` and `describe_next_target`, which the conditions use to put the board into words.

## License

Not yet chosen.

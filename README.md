# System-One Control Bench

![Python 3.11](https://img.shields.io/badge/python-3.11-blue)
![uv](https://img.shields.io/badge/built%20with-uv-purple)
![Ruff](https://img.shields.io/badge/lint-ruff-orange)
![mypy strict](https://img.shields.io/badge/types-mypy%20strict-blue)

> Can a bounded decision model — one that picks an answer from a list rather than writing one, like [Jev](https://docs.typesafe.ai/introduction) — steer an agent across a small grid to a goal?

At every move the player is shown the board as text, asked which way to go, and given the allowed moves as options. A breadth-first solver knows the best moves, so every choice is scored. Simple players mark what a model has to beat.

- [Quick start](#quick-start)
- [Running a benchmark](#running-a-benchmark)
- [Scores](#scores)
- [Conditions](#conditions)
- [Scenarios](#scenarios)
- [Players](#players)
- [Project layout](#project-layout)
- [Extending](#extending)

## Quick start

Needs [uv](https://docs.astral.sh/uv/), which installs Python 3.11 itself. Works on Windows, Linux and WSL2.

```bash
uv sync                      # install
uv run pytest                # run the tests
uv run pre-commit install    # lint, format and type-check on commit; tests on push
cp .env.example .env         # then fill in TYPESAFE_API_KEY (or JEV_API_KEY) for Jev
```

| Command | What it does |
| --- | --- |
| `uv run socb web` | the board viewer, at http://127.0.0.1:8000 |
| `uv run socb benchmark` | plays players on puzzles and saves the results |
| `uv run socb generate` | fills every level with generated puzzles (`--seed` for a fresh set) |
| `uv run socb examples` | rewrites `examples/` after a change of wording |

In the viewer, pick a scenario, a player and a condition, then play one move at a time or to the end. Beside the board is exactly what the player was shown, with the probability it gave each option.

## Running a benchmark

```bash
# The four free players, all 100 puzzles, map condition only
uv run socb benchmark

# Jev, all 100 puzzles, map condition only: up to 1,690 paid calls
uv run socb benchmark --players jev --allow-paid

# Jev, levels 1 to 3 only, map condition only: up to 90 calls
uv run socb benchmark --players jev --levels 1-3 --allow-paid

# Jev, all 100 puzzles, two conditions: up to 3,380 calls
uv run socb benchmark --players jev --conditions map,everything --allow-paid

# Jev, all 100 puzzles, all 10 conditions: up to 16,900 calls
uv run socb benchmark --players jev --conditions all --allow-paid

# Finish a run that stopped or had errors: the same command, plus --resume and its file
uv run socb benchmark --players jev --allow-paid --resume --out benchmarks/<file>.jsonl
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--players` | `random,greedy,greedy-walls,solver` | comma-separated player names |
| `--levels` | `all` | levels to play, such as `3`, `1,4` or `2-5` |
| `--scenarios` | `all` | comma-separated scenario names |
| `--conditions` | `map` | comma-separated [condition](#conditions) names, or `all` |
| `--allow-paid` | off | required for any player that costs money per move |
| `--workers` | `5` | games played at once |
| `--out` | `benchmarks/<date>_<time>_<what was run>.jsonl` | where the results go |
| `--resume` | off | finish the run in `--out` |

**Cost.** Call counts are worst cases: one call per move, every game played to its move limit. A player that wins early costs less. A paid player is refused without `--allow-paid`, and the refusal gives the worst case. Jev takes about 600 input tokens per call under `map` and about 830 under `everything` (measured on level 10). It does not charge for output tokens.

**Output.** Each run writes two files to `benchmarks/`, which is kept in git, named after the date, time and what was run, such as `2026-09-23_18-45_jev_map_levels-1-3`:

- `.jsonl`: one line per game. Each line holds how close the game got to the goal and every move: the options in the order shown, the move chosen, the probability given each option, the best moves, whether the move was one of them, the input and output tokens, the model's own confidence score and version, and how many seconds the answer took.
- `.txt`: the score table.

**Stopping and resuming.** Each game is written the moment it finishes, so a run that crashes or is stopped with Ctrl+C keeps every game it paid for. A run never overwrites a file. Repeat the same command with `--resume --out <file>`: it keeps the finished games and plays the missing ones and those that ended in an error. A Jev call the server turns away (busy, rate-limited or failing) or never receives is tried twice more, after about one and then two seconds; a timeout is not, since the server may have answered and billed it. A call that still fails ends that game as an error, and `--resume` plays the game again.

**Growing a run.** A run on a few levels can be extended to all of them in the same file: run `--levels 1-3 --out <file>`, then the same command without `--levels` and with `--resume`. It keeps the games already played and plays the rest.

**Repeatability.** The options are shuffled at every move, with a seed made from the scenario and the move number. A run is therefore repeatable, every player sees the same order, and no direction always comes first.

## Scores

For each player and condition, the table gives the games won at each level, then these scores over all games. The best of each is in bold, leaving out the solver.

| Score | What it is |
| --- | --- |
| `won` | games that reached the goal before running out of moves |
| `progress` | how much of the way to the goal a game got at its closest, averaged: 1 for a win, 0.5 for a game that got halfway and then lost its way, 0 for one that never got closer than the start |
| `SPL` | success weighted by path length: a won game scores the fewest moves over the moves used, a lost one 0 |
| `errors` | games that ended because the player failed to answer, such as a failed API call. They count as lost, so check this is 0; `--resume` plays them again |

`progress` gives lost games partial credit, and `won` and `SPL` do not. Each move is still saved with `optimal`, which says whether it started a shortest path.

The free players on all 100 puzzles, under `map`:

| Player | won | progress | SPL |
| --- | --- | --- | --- |
| random | 1/100 | 0.28 | 0.01 |
| greedy | 36/100 | 0.44 | 0.36 |
| greedy-walls | 49/100 | 0.58 | 0.49 |
| solver | 100/100 | 1.00 | 1.00 |

## Conditions

A condition is what the player is told. Every condition includes the **map** baseline: the rules, the map with column and row numbers, your position, what you carry, where the objects are, and the question "What is the best next move?". A condition then switches on any of four **ingredients**. Each one is something code works out for the player:

| Ingredient | What the player gets |
| --- | --- |
| `surroundings` | what is next to you in each direction, and where the key, door and goal are relative to you |
| `memory` | every move so far and what it did, so a blocked move doesn't produce the identical prompt again |
| `lookahead` | each option says what that move would do: code looks one move ahead for the player |
| `subgoal` | the question names the next thing to reach: the key, then the door, then the goal |

There are 10 conditions:
- `map` is the baseline.
- The four `map+…` conditions each add one ingredient to it, which shows what that ingredient is worth on its own.
- `everything` has all four ingredients.
- The four `everything-…` conditions each take one away from it, which shows whether that ingredient is still needed once the others are there.

| Condition | surroundings | memory | lookahead | subgoal |
| --- | :---: | :---: | :---: | :---: |
| `map` | | | | |
| `map+surroundings` | ✓ | | | |
| `map+memory` | | ✓ | | |
| `map+lookahead` | | | ✓ | |
| `map+subgoal` | | | | ✓ |
| `everything` | ✓ | ✓ | ✓ | ✓ |
| `everything-surroundings` | | ✓ | ✓ | ✓ |
| `everything-memory` | ✓ | | ✓ | ✓ |
| `everything-lookahead` | ✓ | ✓ | | ✓ |
| `everything-subgoal` | ✓ | ✓ | ✓ | |

`examples/<condition>.json` is the exact body sent to Jev under each condition: the `state`, the `model`, and the `questions`, with the options as the question's `criteria`. Each is taken on `gen-10-01` after one move and one blocked move. Reading these files is the quickest way to see a condition. A test fails when the wording changes, and `uv run socb examples` rewrites them, so every change of wording shows up in the diff.

## Scenarios

A scenario is a YAML file in the folder for its level, such as `scenarios/level-03/key-first.yaml`. The level is the solver's distance to the goal. There are 100 puzzles over 11 levels, spaced out at the top, where each game costs the most calls: 1, 2, 3, 4, 5, 6, 8, 10, 12, 15 and 20. `LEVELS` in `generator.py` sets them.

```yaml
description: The door is ahead of the key, so you have to step north for the key first.
moves_to_goal: 3
map: |
  #####
  #KDG#
  #A###
  #####
```

| Symbol | Meaning |
| --- | --- |
| `#` | wall |
| `.` | floor |
| `A` | agent |
| `G` | goal |
| `K` | key: walking onto it picks it up |
| `D` | locked door: walking into it with the key opens it and steps through |

A game ends once it has used twice the moves the solver needs. The tests check that the solver agrees with each file's stated distance.

Hand-made puzzles are topped up by `socb generate` with random rooms and mazes named `gen-*.yaml`. Generating again with a new `--seed` replaces only the generated ones. From level 3 up, every generated puzzle needs the key, except the one keyless puzzle at level 4 (see the table below).

From level 3 up, a growing share of puzzles is built so that walking straight at the target is not enough: the wall-aware greedy player cannot win them. These are the puzzles that test planning. From level 12 up, every puzzle also has **detours**: moves away from the current target (the key, then the door, then the goal) that every shortest route has to make, like a zigzag through a maze. `LEVEL_KINDS` in `generator.py` sets the mix, and hand-made puzzles count toward the kind they fit.

| Level | Puzzles | Of which the wall-aware greedy player cannot win |
| --- | :---: | --- |
| 1 and 2 | 5 each | none required: a sanity check |
| 3 | 10 | 1, the hand-made `nook` |
| 4 | 10 | 1, without a key (with one, no wrong turn is possible this close to the goal) |
| 5 and 6 | 10 each | 2 |
| 8 | 10 | 5 |
| 10 | 10 | all 10; 5 of them also have a second, longer route to the goal |
| 12 | 10 | all 10, each with at least 2 detours |
| 15 | 10 | all 10, each with at least 3 detours, and 5 of them at least 4 |
| 20 | 10 | all 10, each with at least 5 detours, and 5 of them at least 6 |

Half the puzzles at levels 12, 15 and 20 are also walled in more thickly than usual: two or three rings of wall instead of one, and on one puzzle each at levels 15 and 20, five. The extra rings change nothing about the puzzle, only how much map there is to read, so they test whether a player is thrown by it. `LEVEL_WALLS` in `generator.py` sets them.

## Players

| Player | Paid | How it moves |
| --- | :---: | --- |
| `random` | | a random allowed move |
| `greedy` | | straight at the next target (the key, then the door, then the goal) |
| `greedy-walls` | | like `greedy`, but never into a wall |
| `solver` | | always a best move: the ceiling |
| `jev` | ✓ | asks Jev (`jev-1.13.0`), sending the condition's request |
| `ScriptedPlayer` | | a fixed list of moves; used by the tests and by `examples/`, not in the CLI |

## Project layout

```
src/system_one_control/
├── board.py        Board: the map, where the agent stands, and what it carries
├── rules.py        Rules: the allowed moves, what each does, how to describe it (CompassRules)
├── solver.py       Solver: fewest moves to the goal, and every move that starts such a path
├── scenario.py     Scenario: a board, its rules and its level, loaded from scenarios/
├── request.py      Request: exactly what a player is shown (state, question, options)
├── conditions.py   Condition and CONDITIONS, the ablation
├── players.py      Player and every player, including JevPlayer
├── game.py         Game: one player on one scenario, a Step per move
├── benchmark.py    every scenario × condition × player, played side by side, scored and saved
├── generator.py    PuzzleGenerator: random rooms and mazes at an exact level
├── examples.py     writes examples/
├── cli.py          the socb command
└── web/            the FastAPI viewer
```

## Extending

**A new player.** Subclass `Player`, implement `choose(turn) -> Choice`, and add it to `PLAYERS` in `players.py`.
- A model player must read only `turn.request`, the text it is shown, never `turn.board`.
- If it cannot answer, it may raise: the game records the error and ends.
- A player that holds a connection releases it in `close()`, which is called after every game.

**A new condition.** Add a line to `CONDITIONS` in `conditions.py`, then run `uv run socb examples` to write its example.

**New rules**, such as MiniGrid-style turning or macro moves:
1. Subclass `Rules` and implement `moves`, `apply` and `is_won`.
2. Implement `describe_outcome`, `describe_surroundings` and `describe_next_target`, which the conditions use to put the board into words.
3. Select the rules in a scenario with `rules: <name>`.

## License

Not yet chosen.

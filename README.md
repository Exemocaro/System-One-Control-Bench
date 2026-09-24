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
- [Rules: one step per move, or several](#rules-one-step-per-move-or-several)
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
| `uv run socb examples` | rewrites `examples/` after a change of wording (`--rules` for the other rules) |

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

# Jev, all 100 puzzles, all 10 conditions, each move two steps chosen together: up to 8,800 calls
uv run socb benchmark --players jev --conditions all --rules two-moves --allow-paid

# Finish a run that stopped or had errors: the same command, plus --resume and its file
uv run socb benchmark --players jev --allow-paid --resume --out benchmarks/<file>.jsonl
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--players` | `random,greedy,greedy-walls,solver` | comma-separated player names |
| `--levels` | `all` | levels to play, such as `3`, `1,4` or `2-5` |
| `--scenarios` | `all` | comma-separated scenario names |
| `--conditions` | `map` | comma-separated [condition](#conditions) names, or `all` |
| `--rules` | each scenario's own: `compass` | play every puzzle under these [rules](#rules-one-step-per-move-or-several): `compass`, `two-moves` or `three-moves` |
| `--allow-paid` | off | required for any player that costs money per move |
| `--workers` | `3` | games played at once |
| `--out` | `benchmarks/<date>_<time>_<what was run>.jsonl` | where the results go |
| `--resume` | off | finish the run in `--out` |

**Cost.** Call counts are worst cases: one call per move, every game played to its move limit. A player that wins early costs less. A paid player is refused without `--allow-paid`, and the refusal gives the worst case. Jev takes about 600 input tokens per call under `map` and about 830 under `everything` (measured on level 10). It does not charge for output tokens. Under `two-moves` a condition takes at most 880 calls on all 100 puzzles, and under `three-moves` 620, but each request is longer, because every option is a sequence: about 1.8 times the compass request under `two-moves`, and about 5 times under `three-moves` (measured in characters on level 10).

**Output.** Each run writes two files to `benchmarks/`, which is kept in git, named after the date, time and what was run, such as `2026-09-23_18-45_jev_map_levels-1-3`, with the rules at the end unless they are `compass`:

- `.jsonl`: one line per game. Each line holds the rules, how close the game got to the goal and every move: the options in the order shown, the move chosen, the probability given each option, the best moves, whether the move was one of them, the input and output tokens, the model's own confidence score and version, how many seconds the answer took (for Jev, the answering call alone), and why any earlier attempt was turned away.
- `.txt`: the score table.

**Stopping and resuming.** Each game is written the moment it finishes, so a run that crashes or is stopped with Ctrl+C keeps every game it paid for. A run never overwrites a file. Repeat the same command with `--resume --out <file>`: it keeps the finished games and plays the missing ones and those that ended in an error. A Jev call the server turns away (busy, rate-limited or failing) or never receives is tried twice more, after one and then two seconds, and the move records why each earlier attempt failed; a timeout (120 seconds) is not retried, since the server may have answered and billed it. `--resume` plays a game that ended in an error again from its first move, so its earlier calls are paid for twice. A call that still fails ends that game as an error, and `--resume` plays the game again.

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

Levels and `progress` always count single steps, so they compare across rules; under several-step rules, `progress` takes in every cell a move passed through, not only where it ended. `SPL` and `optimal` count the moves of the game's own rules, so the rate of `optimal` moves does not compare across rules: under `three-moves`, about 4 of the 64 options are best, against 1 or 2 of 4 under `compass`.

The free players on all 100 puzzles, under `map`:

| Player | won | progress | SPL |
| --- | --- | --- | --- |
| random | 4/100 | 0.25 | 0.03 |
| greedy | 28/100 | 0.36 | 0.28 |
| greedy-walls | 37/100 | 0.47 | 0.37 |
| solver | 100/100 | 1.00 | 1.00 |

Under the other rules, `random` wins 2/100 with two-step moves and 6/100 with three-step moves, and `solver` wins every puzzle; the greedy players play compass rules only.

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

## Rules: one step per move, or several

The rules say what a move is. They are chosen for a whole run with `--rules`, and every condition works under each.

| Rules | A move is | Options per move | Fewest moves at level 20 |
| --- | --- | :---: | :---: |
| `compass` | one step north, south, east or west | 4 | 20 |
| `two-moves` | two steps, chosen together, such as `north,east` | 16 | 10 |
| `three-moves` | three steps, chosen together, such as `north,east,east` | 64 | 7 |

Under `two-moves` and `three-moves`:

- Every sequence is offered, blocked or not, just as the compass rules always offer all four directions.
- A blocked step is wasted and the rest are still taken. Reaching the goal ends the move there, so no puzzle is out of reach.
- A puzzle `n` steps away takes `n / 2` or `n / 3` moves, rounded up, and a game still ends at twice that.
- Memory and lookahead describe a move by where it ends and what it picked up, opened or reached, not step by step.
- The subgoal question asks which move *starts* the shortest path to the goal through the target, rather than which is its first step. A move that reaches the key with steps to spare should spend them heading on, and it is scored that way. When the target is the goal, it asks for the shortest path to it.
- Many sequences do the same thing, such as `north,south` and `east,west`: at the start of a puzzle the 64 three-step options have a median of 8 different outcomes, and the 16 two-step ones 5. They are all offered, since merging them would tell the player where the walls are, so a model's probability is split across them. Add it up by outcome before comparing it with `compass`.

`examples/two-moves/` and `examples/three-moves/` hold the requests under each, written by `uv run socb examples --rules <rules>`.

The sequences test whether Jev does better when one decision covers several steps. A slide (walk until something stops you) was tried first and dropped: with nothing to stop on in open rooms and mazes, 21 of the 100 puzzles could not be won.

## Scenarios

A scenario is a YAML file in the folder for its level, such as `scenarios/level-02/gen-02-01.yaml`. The level is the solver's distance to the goal. There are 100 puzzles over 11 levels, spaced out at the top, where each game costs the most calls: 1, 2, 3, 4, 5, 6, 8, 10, 12, 15 and 20. `LEVELS` in `generator.py` sets them.

```yaml
description: A generated 6x6 room without a key, with a wall in the way of walking straight at the goal.
moves_to_goal: 2
map: |
  ######
  #G#.##
  #.A..#
  ##...#
  ##...#
  ######
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

Every puzzle is generated by `socb generate`, as a random room or maze named `gen-*.yaml`, except `maze` at level 10, which is hand-made. Generating again with a new `--seed` replaces only the generated ones. From level 3 up, a generated puzzle needs the key unless its kind says otherwise.

Each level mixes kinds of puzzle, set by `LEVEL_KINDS` in `generator.py`; a hand-made puzzle counts toward the kind it fits:

- **Needs planning**: walking straight at the target (the key, then the door, then the goal) is not enough, so the wall-aware greedy player cannot win it.
- **Wall in the way**, without a key: a wall blocks one of the first steps toward the goal, so a player that does not check for walls walks into it.
- **Goes round a wall**, without a key: every shortest route has to turn away from the goal to get round a wall. Turning away and back costs two moves, so this is possible from level 4.
- **Detours**: the moves away from the current target that every shortest route has to make, like a zigzag through a maze.

| Level | Puzzles | What they include | The wall-aware greedy player loses |
| --- | :---: | --- | :---: |
| 1 | 5 | anything: a sanity check | 0 |
| 2 | 5 | 3 with a wall in the way | 0 |
| 3 | 10 | 3 with a wall in the way; 1 that needs planning, without a key | 1 |
| 4 | 10 | 3 that go round a wall; 1 that needs planning, without a key (with a key, no wrong turn is possible this close to the goal) | 4 |
| 5 | 10 | 3 that go round a wall; 2 that need planning | 5 |
| 6 | 10 | 3 that go round a wall twice; 2 that need planning | 5 |
| 8 | 10 | 3 that go round a wall twice; 5 that need planning | 8 |
| 10 | 10 | all need planning; 5 also have a second, longer route to the goal | 10 |
| 12 | 10 | all need planning, each with at least 2 detours | 10 |
| 15 | 10 | all need planning, each with at least 3 detours, and 5 of them at least 4 | 10 |
| 20 | 10 | all need planning, each with at least 5 detours, and 5 of them at least 6 | 10 |

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
├── rules.py        Rules: the allowed moves, what each does, how to describe it (CompassRules, and
│                   TwoMoveRules and ThreeMoveRules for steps chosen several at a time)
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

**New rules**, such as MiniGrid-style turning:
1. Subclass `Rules` and implement `moves`, `apply` and `is_won`.
2. Implement `describe_outcome`, `describe_surroundings` and `describe_next_target`, which the conditions use to put the board into words.
3. If a move is several steps of other rules, return those rules from `step_rules` and say how many moves a level takes in `moves_for`, so levels and progress keep counting single steps.
4. Add them to `RULES` in `rules.py`, then play them with `--rules <name>`, or select them in a scenario with `rules: <name>`.

## License

Not yet chosen.

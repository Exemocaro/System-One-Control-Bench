# Details

The parts of the README that most users do not need: cost, output files, stopping and resuming, the players, local models and extending the code.

## Benchmark commands

```bash
uv run socb benchmark                                                       # free players, map only
uv run socb benchmark --players jev --allow-paid                            # Jev, map only: up to 1,690 calls
uv run socb benchmark --players jev --levels 1-3 --allow-paid               # levels 1 to 3: up to 90 calls
uv run socb benchmark --players jev --conditions all --allow-paid           # all 10 conditions: up to 16,900 calls
uv run socb benchmark --players jev --conditions all --rules two-moves --allow-paid   # up to 8,800 calls
uv run socb benchmark --players jev --allow-paid --resume --out benchmarks/<file>.jsonl   # finish a run
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--players` | `random,greedy,greedy-walls,solver` | comma-separated player names |
| `--levels` | `all` | such as `3`, `1,4` or `2-5` |
| `--puzzles` | `all` | comma-separated puzzle names |
| `--conditions` | `map` | condition names, or `all` |
| `--track` | none | `core`: compass rules, `map` and `everything`, all 100 puzzles (the [leaderboard](../SUBMITTING.md) track); cannot be combined with `--conditions` or `--rules` |
| `--rules` | each puzzle's own, `compass` | `compass`, `two-moves`, `three-moves`, `up-to-two-moves`, `up-to-three-moves` |
| `--players-file` | `./players.toml` if present | extra chat and decision players, see [SUBMITTING.md](../SUBMITTING.md) |
| `--allow-paid` | off | required for any player that costs money per move |
| `--workers` | `3` | games played at once |
| `--out` | `benchmarks/<date>_<time>_<what>.jsonl` | where results go |
| `--resume` | off | finish the run in `--out` |

The other commands: `socb examples [--rules <name>]` writes what each condition shows the player to `examples/`, `socb generate [--per-level N] [--seed N]` tops up the puzzles, `socb web` opens the viewer, `socb exam` runs the exam, `socb validate <file>` replays a results file and checks every option, answer and score, `socb submit <file> --kind ...` writes a leaderboard entry from a core-track file, and `socb leaderboard` rebuilds the leaderboard table and page from the entries (see [SUBMITTING.md](../SUBMITTING.md)).

## Exam

In a game each model reaches different positions, so its optimal-move rate mixes decision quality with where it went. The exam asks every model the same positions once: an item is a puzzle plus a short prefix of moves played from the start (`start`, `on-route`, `off-route`, `after-blocked`, `late`). Playing the prefix with the ordinary game gives the board and the history, so every condition renders exactly as in a real game; then the model answers one move. `exam/items.jsonl` holds the 495 items (5 per puzzle, 4 at level 1), made once by `scripts/make_exam.py`.

```bash
uv run socb exam --players solver --conditions map,everything   # one answer per item and condition
```

`--conditions` defaults to `map`; the committed runs use `map,everything`, so repeat them with that flag. Answers go to `exam/<date>_<time>_<what was run>.jsonl`, one record per item, condition and player, with the item, the move record and any error; `--workers`, `--allow-paid` and `--resume` work as in `socb benchmark`.

## Cost

Call counts are worst cases: one call per move, every game played to its move limit. A paid player is refused without `--allow-paid`, and the refusal gives the worst case.

- Jev takes about 600 input tokens per call under `map` and 830 under `everything` (level 10). It does not charge for output tokens.
- Under `two-moves` a condition takes at most 880 calls on all 100 puzzles, and under `three-moves` 620. Each request is longer: about 1.8 times the compass request under `two-moves`, about 5 times under `three-moves` (characters, level 10). The `up-to-` rules take at most as many calls as the rules they extend.
- Gemma 4 26B costs $0.09 per million input tokens and $0.30 per million output tokens; DeepSeek V4.1 Flash $0.14 and $0.42 (September 2026).

## Output

Each run writes two files to `benchmarks/`, named after the date, time and what was run:

- `.jsonl`, the results file: one line per game with the puzzle, condition, player, level, rules, whether it was won, how close it got, and every move (options in the order shown, move chosen, probability per option, best moves, whether the move was optimal, tokens, cost where reported, the model's confidence and version, seconds, and why any earlier attempt was turned away).
- `.txt`: the score table.

## Stopping and resuming

Each game is written the moment it finishes, so a crash or Ctrl+C keeps every finished game; calls made in a game still under way are lost. A run never overwrites a file. Repeat the command with `--resume --out <file>` to keep finished games and play the missing and errored ones (errored games restart from the first move, so their earlier calls are paid twice). A run may resume a file whose games are a subset of what it would play, so more levels, puzzles, conditions or players are fine. It refuses a file holding games this run would not play, or games played under other rules.

A Jev call the server turns away is tried twice more, after one and two seconds. A timeout (120 s) is not retried, since the server may have billed it. OpenRouter calls are retried after 5, 15, 30 and 60 seconds. A call that still fails ends that game as an error.

**Repeatability.** Options are shuffled at every move with a seed from the puzzle name and the move number, so every player and condition sees the same option order at the same move of the same puzzle (different routes still reach different positions).

## Players

| Player | Paid | How it moves |
| --- | :---: | --- |
| `random` | | a random offered move |
| `greedy` | | straight at the next target (key, door, goal), compass rules only |
| `greedy-walls` | | like `greedy`, never into a wall, compass rules only |
| `solver` | | always a best move |
| `jev` | ✓ | asks Jev (`jev-1.13.0`) |
| `laya` | | [Laya](https://huggingface.co/convaiinnovations/laya), `typed-decisions`, on this machine |
| `gliclass` | | [GLiClass](https://huggingface.co/knowledgator/gliclass-modern-large-v3.0), on this machine |
| `qwen3.5-4b` | | [Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B), on this machine, scored on option-number probabilities |
| `gemma-4-26b` | ✓ | Gemma 4 26B on OpenRouter, reasoning off |
| `deepseek-v4.1-flash` | ✓ | DeepSeek V4.1 Flash on OpenRouter, reasoning off |
| `gemma-4-26b-think`, `deepseek-v4.1-flash-think` | ✓ | the same with reasoning, capped at 1,024 reasoning tokens |

- **Laya** gets the question and option texts without ids (it allows 48 tokens per option; a longer option ends the game as an error). Its token budget is stretched to the whole request.
- **GLiClass** reads the state as text, the question as task prompt and the option texts as labels. Scores are scaled to sum to 1.
- **Qwen3.5-4B** is sent the chat the OpenRouter models get, with thinking off, plus the start of the answer. It writes nothing: each option's probability is read from its odds for the digits of the option number.
- **Chat models** are pinned to DeepInfra on OpenRouter, which fixes the provider; it does not guarantee identical answers or an unchanged deployment. A JSON schema holds the answer to one option id. Without reasoning the answer may use 64 tokens; a model that thinks anyway ends the game as an error. An answer cut off by a cap is an error. No temperature or top_p is sent, so the provider's defaults apply and answers vary between identical calls. Chat answers carry no probabilities.

## Local models

`uv sync --extra local` installs PyTorch. On Windows it comes from PyTorch's CUDA 13.0 index (NVIDIA driver 580 or later; without a GPU it runs on the CPU). A plain `uv sync` removes it again, so run local players with `uv run --extra local socb benchmark --players laya`. Each model downloads from Hugging Face on first use (about 800 MB for Laya and GLiClass, 9 GB for Qwen3.5-4B) and is shared by every game.

On an RTX 5070 Ti laptop GPU a Laya move takes about 0.1 s and a GLiClass move 0.3 s; Qwen3.5-4B takes 0.2 s with 4 options and 1.7 s with 84. On a 20-core CPU Laya takes about 1 s under `compass` and 5 to 6 s under `three-moves`. `SOCB_DEVICE` in `.env` picks `cpu` or `cuda`. Qwen3.5-4B needs 9 GB of GPU memory; on a 12 GB GPU play it alone, since too little free memory can make the driver reset and end every game under way in an error (`--resume` plays them again).

## Rules, in more detail

- Every sequence is offered, blocked or not. A blocked step is wasted and the rest are taken. Reaching the goal ends the move there, so every puzzle stays winnable.
- A puzzle `n` steps away takes `n / 2` or `n / 3` moves, rounded up; a game ends at twice that. Levels and `progress` count single steps, so they compare across rules. The rounding matters for the budget: a 4-step puzzle allows 8 compass moves (8 steps) but 4 three-step moves (up to 12 steps), so sequence rules can give a game more steps than compass rules.
- The solver minimises the number of moves (decisions), not steps, and keeps ties. A move with a wasted or blocked step is therefore optimal when it still finishes in the fewest moves. The fixed-length rules ask "Which move starts the shortest path to ...?" (shortest in moves, ties kept) and the `up-to-` rules ask for the fewest turns. The prompts are frozen, since every run depends on them.
- Memory and lookahead describe a move by where it ends. The subgoal question asks which move *starts* the shortest path (under the `up-to-` rules: the one that gets there in the fewest turns).
- Many sequences have the same outcome (`north,south` and `east,west`). At the start of a puzzle the 64 three-step options have a median of 8 outcomes, the 16 two-step options 5. They are all offered, so a model's probability is split across them; add it up by outcome before comparing with `compass`.
- `optimal` does not compare across rules: under `three-moves` about 4 of 64 options are best, against 1 or 2 of 4 under `compass`.
- A slide (walk until something stops you) was tried and dropped: 21 of the 100 puzzles could not be won.

## Puzzle kinds

Each level mixes kinds, set by `LEVEL_KINDS` in `puzzles.py`:

- **Needs planning**: walking straight at the next target is not enough, so the wall-aware greedy player cannot win.
- **Wall in the way** (no key): a wall blocks one of the first steps toward the goal.
- **Goes round a wall** (no key): every shortest route turns away from the goal first. Possible from level 4.
- **Detours**: moves away from the current target that every shortest route has to make. Levels 12, 15 and 20 need at least 2, 3 and 5.

Half the puzzles at levels 12, 15 and 20 have a thicker outer wall (`LEVEL_WALLS`), which changes nothing about the puzzle but tests whether irrelevant map text throws a player. `maze` at level 10 is hand-made; the rest are generated.

| Level | Puzzles | Greedy-walls loses |
| --- | :---: | :---: |
| 1, 2 | 5 each | 0 |
| 3 | 10 | 1 |
| 4 | 10 | 4 |
| 5, 6 | 10 each | 5 |
| 8 | 10 | 8 |
| 10, 12, 15, 20 | 10 each | 10 |

## Project layout

```
src/system_one_control/
├── world.py        Position, Board, Move; Rules: the allowed moves, what each does, how to
│                   describe it (CompassRules, and SequenceRules for several steps chosen at
│                   a time, such as TwoMoveRules); Solver: fewest moves, best moves
├── puzzles.py      Puzzle: a board, its rules and its level, loaded from puzzles/;
│                   PuzzleGenerator: random rooms and mazes at an exact level
├── prompts.py      Option, Request: exactly what a player is shown (state, question, options);
│                   Condition and CONDITIONS, the ablation
├── examples.py     writes examples/
├── exam.py         the fixed-state exam: plays every model on the same positions
├── exam_items.py   picks the exam positions (used by scripts/make_exam.py)
├── leaderboard.py  entries from submitted core runs, and the table and page built from them
├── players/
│   ├── base.py     Turn, Choice, Player, and the settings read from .env
│   ├── baselines.py the players that read the board: Random, Scripted, Solver, Greedy
│   ├── remote.py   JevPlayer, and LLMPlayer: chat models on OpenRouter
│   ├── local.py    LayaPlayer, GLiClassPlayer and LocalLLMPlayer, which run on this machine
│   └── __init__.py PLAYERS: every player by name
├── bench.py        Game: one player on one puzzle, a Played per move; every
│                   puzzle × condition × player, played side by side, scored and saved
├── cli.py          the socb command
└── web/            the FastAPI viewer

benchmarks/         results of the runs in the paper (.jsonl and .txt)
exam/               exam items and the exam results
examples/           the exact request each condition sends
leaderboard/        entries, core-track results, players endpoint example, the generated table
analysis/           recomputes every table and figure of the paper from the results files
paper/              the Typst source of the report
scripts/            make_exam.py, which made exam/items.jsonl
```

## Extending

- **A new player.** Subclass `Player`, implement `choose(turn) -> Choice`, and add it to `PLAYERS` in `players/__init__.py`. A chat model on OpenRouter needs only a line in `LLM_MODELS` in `players/remote.py`, and a model run on this machine a line in `LOCAL_LLM_MODELS` in `players/local.py`. A model must read only `turn.request`. If it cannot answer it may raise: the game records the error and ends. A player holding a connection releases it in `close()`.
- **A chat model or decision endpoint without code.** Add it to a `players.toml` (`--players-file`); the keys are listed in [SUBMITTING.md](../SUBMITTING.md).
- **A new condition.** Add a line to `CONDITIONS` in `prompts.py`, then `uv run socb examples`. A test fails when the wording changes, so every change shows in the diff.
- **New rules.** Subclass `Rules` in `world.py` (`moves`, `apply`, `is_won`, `describe_outcome`, `describe_surroundings`, `describe_next_target`; override `subgoal_question` if needed). If a move is several steps of other rules, return them from `step_rules` and set `moves_for`. Add them to `RULES`, then `uv run socb examples --rules <name>`. The examples play two moves first, a move and then a blocked one; `EXAMPLE_MOVES` in `examples.py` picks them.

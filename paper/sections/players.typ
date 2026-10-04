#import "../lib.typ": todo

= Evaluation protocol <sec:protocol>

== Models and baselines

We compare three kinds of player: non-generative decision models (Jev, Laya Typed-Decisions and GLiClass); a generative model used through option scoring, which generates nothing here (Qwen3.5-4B @qwen2026); and chat models that generate an option ID (Gemma 4 26B @gemma2026 and DeepSeek V4.1 Flash @deepseek2026).

Random chooses uniformly from the offered actions. Greedy moves toward the next target, and greedy-walls also avoids walls. The solver always chooses an optimal move. The greedy baselines use compass moves only. Each model sees the request without direct access to the environment or solver.
// src: src/system_one_control/players/baselines.py; src/system_one_control/players/base.py

Jev (`jev-1.13.0`) chooses the option with the highest returned probability. GLiClass scores the option texts independently, using the state as classification text and the question as the task. The controller normalises these scores to sum to 1. Qwen3.5-4B scores option numbers in its chat template and selects the most likely one.
// src: src/system_one_control/players/local.py; src/system_one_control/players/remote.py

Laya receives the state, question and option texts, with option IDs omitted. Requests above 8,192 tokens or options above 48 tokens are rejected rather than truncated. The Typed-Decisions checkpoint was trained for four workflow domains and warns about transfer and large option sets @layacard.
// src: src/system_one_control/players/local.py; paper/references.bib

Gemma and DeepSeek use OpenRouter with DeepInfra as the fixed host and JSON-schema output constrained to an option ID. Direct answers have reasoning off. DeepSeek V4.1 Flash (reasoning) permits 1,024 reasoning tokens. Every model has compass results; sequence-rule results exist for Jev, Gemma 4 26B, Laya and GLiClass only (Qwen3.5-4B and both DeepSeek configurations ran compass moves only).

A missing, invalid or capped answer ends the game as an error and counts as a loss. All 242 evaluated combinations of player, action rules and input condition have zero errors in the retained records. Transient failures occurred; errored games were replayed with `--resume`. Option order is shuffled with a seed from the puzzle and move number. @app:history records prompt development and the later question correction; @app:reproducibility gives the inference and replay checks.
// src: src/system_one_control/players/remote.py; analysis/out/coverage.csv; analysis/manifest.toml

== Metrics and statistics

Success rate is the share of games reaching the goal within the move limit (the `won` field in the records). The limit is twice the solver's fewest moves. Progress is one minus the closest compass-step distance reached divided by the starting distance. Final-state progress uses the ending position and can be negative. SPL is zero for a loss; for a win, it divides the fewest moves by the larger of that number and the moves used @anderson2018evaluation. SPL and the limit count model decisions. Optimality minimises decisions and accepts every tied best move, including sequences with wasted steps.
// src: analysis/README.md; src/system_one_control/world.py

Intervals use 10,000 puzzle resamples and the 95% percentile-bootstrap interval. They describe variation across the evaluated puzzle collection, not repeated calls. Component comparisons pair the same puzzles. McNemar's exact test compares game completion; Holm correction covers eight component contrasts per model. Every evaluated model/input has 100 games.
// src: analysis/README.md; analysis/out/coverage.md

We test whether the selected option's probability predicts solver-optimality. This is an operational confidence diagnostic, not a complete test of the returned action distribution. Ten-bin ECE and binary Brier score use this target @guo2017calibration. Two tied best moves at 0.5 each give an optimal chosen move a score of 0.5. GLiClass supplies normalised independent scores; Qwen supplies option-number token probabilities, so their origins differ.
// src: analysis/out/calibration.md; src/system_one_control/players/local.py

The exam uses 495 scripted compass positions from 100 puzzles. Each model answers once per item under map alone and full context (990 answers). Prefixes use the ordinary game, preserving history and option shuffles. Errors are incorrect; any solver-best move is optimal. Rates average within puzzles, then equally over puzzles. @app:reproducibility gives item counts and construction details.
// src: scripts/make_exam.py; src/system_one_control/exam.py; analysis/out/exam.md

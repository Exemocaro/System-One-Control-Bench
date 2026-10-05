# analysis

Every table and figure in the paper, recomputed from the saved results files. No API calls.

    uv run --with matplotlib python analysis/analyze.py      # writes analysis/out/ (about 20 s)
    uv run --with matplotlib pytest analysis -q

- `manifest.toml`: which results file holds each player under each rules, and each player's exam file. Add a run here,
  nothing else.
- `metrics.py`: the numbers, as small pure functions.
- `analyze.py`: loads the games, writes the tables (`out/*.md` and `.csv`) and the figures (`out/fig_*.png` and `.pdf`).
- `test_metrics.py`: one table test per metric.

## Rules for changing this folder

Keep it this small. These rules are enforced by `test_the_folder_stays_small`.

- Three Python files, no more. A new metric is a function in `metrics.py` with one table test. A new table or
  figure is one function in `analyze.py`.
- `analyze.py` stays under 660 lines (as formatted by ruff). Make room by removing something before you add something.
- Only what the paper uses. Exploratory scripts stay out of the repository.
- Do not add options, classes, caches or configuration.
- One colour and one display name per model, both in `PLAYERS`. The prose names of the inputs are in `COMPONENTS`
  and `INPUTS`.

## Definitions

- **Success rate**: the share of games that reach the goal (the `won` field).
- **Progress**: 1 − d/level, where d is the closest the game ever came to the goal, counted in single compass steps. The
  start counts, so progress is never below 0. A game can earn progress and then wander off.
- **Final-state progress**: the same, measured where the game ended. It is negative when the game ended farther from
  the goal than it started.
- **SPL**: fewest moves / max(fewest, moves used) for a win, else 0. It counts moves (model decisions), so a two-step
  move counts once.
- **Blocked moves**: the share of moves that left the board unchanged, such as walking into a wall or into a locked
  door without the key.
- **Intervals**: 95% bootstrap intervals over puzzles: redraw the 100 puzzles with repeats 10,000 times (seed 0),
  recompute, and keep the middle 95%. Each game is one puzzle.
- **Component effects**: positive means that including the component helps. For "added to map only" the effect is
  map+X − map. For "removed from full context" it is everything − (everything−X). Each effect is a paired difference
  over the same puzzles. The p-value is McNemar's exact test on won, Holm-adjusted over the 8 comparisons of each model.
- **Calibration**: confidence is the probability the model gave its chosen move. The outcome is whether that move was
  optimal, where any of several tied best moves counts. This is computed on compass moves only, pooling all ten
  conditions, and the bins have equal width. Jev's own `confidence` field is (p_max − 1/n)/(1 − 1/n), a rescaled top
  probability, so it is not reported separately.
- **Exam**: every player answers the same 495 fixed positions (`exam/items.jsonl`) once per input. The optimal rate is
  averaged within each puzzle and then over puzzles, so intervals resample puzzles; an error counts as not optimal.
  "Own games optimal rate" is the share of optimal moves in the player's own compass games under the same input,
  averaged within each game and then over puzzles, as the exam is; "every move equal" weighs long games more.
  `pairs` gives paired differences (puzzle bootstrap) between Jev, Gemma and DeepSeek on success rate and on the exam.
- **Brier of a constant**: p(1 − p) at the model's optimal share, the score of always predicting that share.
- **Hypotheses**: H1–H7 were written on 23 September, before the main evaluation (paper, Appendix B). Each criterion
  is checked as written; the observed column says where a criterion proves less than its wording. They use older
  names: interaction history = move history (`memory`), simulated action outcomes = move outcomes (`lookahead`).

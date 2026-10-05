#import "../lib.typ": todo

= Players and measures <sec:protocol>

== Players

We call anything that plays a game a *player*: seven model setups and four baselines (@tab:players). The models see only the text of each request. The baselines read the board directly and ignore the input condition.

#figure(table(columns: (auto, 1fr), align: left, stroke: none, inset: 2.5pt,
  table.header([Player], [What it is and how it chooses]),
  table.cell(colspan: 2)[_Non-generative decision models: return a probability for each option; we play the highest_],
  [Jev], [TypeSafe's hosted decision model (`jev-1.13.0`).],
  [Laya], [Laya's Typed-Decisions checkpoint, an open model built to answer the same kind of request as Jev, run locally @layacard.],
  [GLiClass], [An open classifier that can score any list of labels without training on them @stepanov2025gliclass, run locally. It scores each option text as a label; we scale the scores to sum to 1.],
  table.cell(colspan: 2)[_Chat models_],
  [Qwen3.5-4B], [A small open chat model @qwen2026, run locally. It writes nothing: we read the probability it gives each option number and play the highest.],
  [Gemma 4 26B], [Answers with an option number @gemma2026.],
  [DeepSeek V4.1 Flash], [Answers with an option number, without reasoning @deepseek2026.],
  [DeepSeek V4.1 Flash (reasoning)], [The same model, allowed to reason for up to 1,024 tokens before answering.],
  table.cell(colspan: 2)[_Baselines_],
  [Solver], [Always plays an optimal move.],
  [Greedy], [Steps toward its next target (the key, then the door, then the goal), ignoring walls.],
  [Greedy (walls)], [Like Greedy, but never walks into a wall.],
  [Random], [Picks one of the offered options at random.]),
  placement: none, caption: [The players.]) <tab:players>
// src: src/system_one_control/players/baselines.py; src/system_one_control/players/local.py; src/system_one_control/players/remote.py

Random shows what chance achieves: it wins 4 of 100 compass games, all at levels 1 to 3. A model that does no better than Random is not making use of the input. Greedy and Greedy (walls) show how far one gets by heading straight for the target without planning; they play compass moves only. Random and Solver play under every move rule.
// src: analysis/out/levels.md; analysis/manifest.toml

Every model gets the same request: the state, the question and the options. Jev receives these as the fields of its API. Laya receives the state, the question and the option texts without their numbers, because it would otherwise spend part of each option's allowance of 48 tokens (the word pieces a model reads) on the number. Gemma and DeepSeek run through OpenRouter, always on the DeepInfra host. They receive the request as one chat message, and their answer must be JSON naming one option. Qwen3.5-4B receives the same chat, followed by the start of that JSON answer, `{"option": "option_`. Qwen, Laya and GLiClass give the same answer every time they are asked; Jev and the chat models do not (@app:reproducibility).
// src: src/system_one_control/players/local.py; src/system_one_control/players/remote.py

The options are shuffled at every move, with a seed made from the puzzle and the move number, because models can prefer an option for its position or its label @zheng2024selection. If a model gives no valid answer, the game ends and counts as a loss. Some calls failed for passing reasons such as network errors; we replayed those games, so the final records have no errors in any of the 262 combinations of player, move rules and input condition. Every model played compass rules under all ten conditions. Jev, Laya, GLiClass and Gemma 4 26B also played the four sequence rules, and Qwen3.5-4B played `two-moves` and `up-to-two-moves` (its two three-step rules were not run). Both DeepSeek setups played compass only, to limit cost.
// src: src/system_one_control/bench.py; analysis/out/coverage.csv; analysis/manifest.toml

Before the main runs, we wrote down seven hypotheses about Jev. @app:hypotheses lists them with the results.

== Measures

Every condition has 100 games per player, one per puzzle.

- *Success rate:* the share of games won.
- *Progress:* how close to the goal the piece ever got. Distance is the number of steps the solver would still need from a position, and progress is 1 − (closest distance reached / distance at the start). It is 0 if the piece never got closer than where it started, and 1 if it reached the goal. Because it uses the closest point, even aimless wandering earns some progress: Random's is 0.25.
- *Final-state progress:* the same, but measured where the game ended. It is negative if the piece ended farther from the goal than it started.
- *SPL* (success weighted by path length) @anderson2018evaluation: 0 for a lost game; for a won game, the fewest moves needed divided by the moves used. An SPL of 1 means every game was won by a shortest route.
- *Blocked moves:* the share of moves that leave the piece where it was.
- *Optimal-move rate:* the share of a player's moves that are optimal, worked out for each game and then averaged over games.
// src: analysis/README.md; analysis/metrics.py; src/system_one_control/world.py

== Statistics

*Intervals.* The 95% intervals in brackets show how much a result depends on which puzzles happen to be in the set. We compute them by resampling: draw 100 puzzles from the 100 at random, allowing repeats, recompute the result, repeat this 10,000 times, and keep the middle 95% of the results (a bootstrap interval). These intervals do not show how much a rerun would vary.

*Comparisons.* Two inputs or two models are always compared on the same 100 puzzles, puzzle by puzzle, and the difference gets an interval computed the same way. For the effect of each component on success rate, we also use McNemar's exact test. It looks only at the puzzles won with one input and lost with the other, and asks how likely such a lopsided split would be by chance. Each model gets eight of these tests, so we apply the Holm correction, which raises the p-values so that the chance of any false alarm among the eight stays at 5%. We call an effect *significant* when its corrected p-value is below 0.05.
// src: analysis/README.md; analysis/metrics.py

*Probabilities.* Jev, Laya, GLiClass and Qwen3.5-4B give a probability for every option. We check whether the probability of the chosen move matches how often such moves are optimal (calibration @guo2017calibration). For the *expected calibration error* (ECE), the moves are sorted into ten bins by that probability (0--0.1, 0.1--0.2, and so on). In each bin we compare the average probability with the share of optimal moves, and ECE is the average gap, weighted by the size of each bin. The *Brier score* is the average squared difference between the probability and the outcome (1 if the move was optimal, 0 if not). For both, lower is better and 0 is perfect. When two moves are equally good, a model that gives each a probability of 0.5 looks underconfident on these measures, although either choice is optimal.
// src: analysis/metrics.py; analysis/out/calibration.md

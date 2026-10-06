#import "../lib.typ": todo

= Players and measures <sec:protocol>

== Players

We call anything that plays a game a *player*: seven model setups and four baselines (@tab:players). The models see only the text of each request. The baselines do not read the request: they look at the board directly, so the condition makes no difference to them.

#let group(body) = table.cell(colspan: 2, fill: luma(235), inset: (x: 4pt, y: 3.5pt))[*#body*]
#figure(table(columns: (auto, 1fr), align: left, stroke: none, inset: (x: 4pt, y: 2.5pt),
  table.hline(stroke: 0.8pt),
  table.header([*Player*], [*What it is and how it chooses*]),
  table.hline(stroke: 0.5pt),
  group[Non-generative decision models: return a probability for each option; we play the highest],
  [Jev], [TypeSafe's hosted decision model, `jev-1.13.0`.],
  [Laya], [Laya's open Typed-Decisions model, built for the same kind of request as Jev @layacard. Run locally.],
  [GLiClass], [An open classifier that scores any list of labels @stepanov2025gliclass; each option text is one label, and we scale the scores to sum to 1. Run locally.],
  group[Chat models: answer with an option number],
  [Qwen3.5-4B], [A small open chat model @qwen2026. Run locally; we read the probability it gives each option number.],
  [Gemma 4 26B], [A chat model from Google @gemma2026, reasoning off.],
  [DeepSeek V4.1 Flash], [A chat model from DeepSeek @deepseek2026, reasoning off.],
  [DeepSeek V4.1 Flash (reasoning)], [The same model, allowed to reason for up to 1,024 tokens before answering.],
  group[Baselines: read the board directly],
  [Solver], [Always plays an optimal move.],
  [Greedy], [Takes the step that most shortens the distance to its next target, counted as if there were no walls, even when that step walks into a wall. The next target is the key while it lies on the map, then the locked door, then the goal.],
  [Greedy (walls)], [Like Greedy, but never takes a step into a wall.],
  [Random], [Picks one of the offered options at random.],
  table.hline(stroke: 0.8pt)),
  placement: none, caption: [The players.]) <tab:players>
// src: src/system_one_control/players/baselines.py; src/system_one_control/players/local.py; src/system_one_control/players/remote.py; src/system_one_control/world.py

Random shows what chance achieves: it wins 4 of 100 compass games, all at levels 1 to 3. It is the reference for a player that does not use the request at all. Greedy and Greedy (walls) show how far one gets by heading straight for the target without planning; they play compass moves only. Random and Solver play under every move rule.
// src: analysis/out/levels.md; analysis/manifest.toml

Every model gets the same request: the state, the question and the options. Jev receives these as the fields of its API. Laya receives the state, the question and the option texts without their numbers, because it would otherwise spend part of each option's allowance of 48 tokens (the word pieces a model reads) on the number. Gemma 4 26B and both DeepSeek V4.1 Flash setups @deepseekopenrouter run through OpenRouter, always on the DeepInfra host. They receive the request as one chat message and must answer in JSON that names one of the offered options; the provider holds the answer to that list. Qwen3.5-4B receives the same chat, followed by the start of that answer, `{"option": "option_`. We then read the probability of each option number as the model would write it, digit by digit (so `84` takes two digits), counting only the numbers on offer and scaling them to sum to 1. Qwen3.5-4B therefore always names a valid option.
// src: src/system_one_control/players/local.py; src/system_one_control/players/remote.py

The options are shuffled at every move, with a seed made from the puzzle and the move number, because models can prefer an option for its position or its label @zheng2024selection. If a model gives no valid answer, the game ends and counts as a loss. Some calls failed because of temporary problems such as network errors; we played those games again, so the final records have no errors in any of the 282 combinations of player, move rules and condition. Every model played compass rules under all ten conditions. Jev, Laya, GLiClass, Gemma 4 26B and Qwen3.5-4B also played the four sequence rules. Both DeepSeek setups played compass only, to limit cost.
// src: src/system_one_control/bench.py; analysis/out/coverage.csv; analysis/manifest.toml

Some models answer an identical request the same way every time, and others do not. We checked this by asking models again at positions from their own recorded games (@app:reproducibility). Qwen3.5-4B, Laya and GLiClass gave exactly the same probabilities. Jev and DeepSeek V4.1 Flash did not, so a rerun of them would play different games. Gemma 4 26B and DeepSeek V4.1 Flash (reasoning), which also use the provider's default sampling settings, were not checked.
// src: scripts/replay_check.py; paper/sections/reproducibility.typ

Before the main runs, we wrote down seven hypotheses about Jev. @app:hypotheses lists them with the results.

== Measures

Every condition has 100 games per player, one per puzzle.

- *Success rate:* the share of games won.
- *Progress:* how close to the goal the agent ever got. Distance is the number of steps the solver would still need from a position, and progress is 1 − (closest distance reached / distance at the start). It is 0 if the agent never got closer than where it started, and 1 if it reached the goal.
- *Final-state progress:* the same, but measured where the game ended. It is negative if the agent ended farther from the goal than it started.
- *SPL* (success weighted by path length) @anderson2018evaluation: 0 for a lost game; for a won game, the fewest moves needed divided by the moves used. An SPL of 1 means every game was won by a shortest route.
- *Blocked moves* (compass rules only): the share of moves that change nothing, because the step runs into a wall or into the locked door without the key.
- *Optimal-move rate:* the share of a player's moves that are optimal, worked out for each game and then averaged over games.
// src: analysis/README.md; analysis/metrics.py; src/system_one_control/world.py

== Statistics <sec:statistics>

*Intervals.* We report 95% bootstrap intervals, in brackets, to show how sensitive the results are to the puzzles included in the evaluation. We repeatedly draw 100 puzzles from the original set, allowing a puzzle to appear more than once, and recalculate the score using the recorded results. After 10,000 repetitions, we take the 2.5th and 97.5th percentiles as the interval limits. This procedure gives some puzzles more weight and leaves others out. It does not generate new puzzles or rerun the models, so it does not measure how much repeated calls on the same puzzles would vary.

*Comparisons.* We compare models and conditions puzzle by puzzle. In each bootstrap repetition, we use the same sampled puzzles for both sides and calculate the difference between their scores. For example, Jev wins 4 percentage points fewer games than Gemma 4 26B with full context, with an interval of [−10, 2]. This range includes an advantage for either model, so the comparison does not establish which performs better beyond the recorded run.

To test whether a component affects success rate, we use McNemar's exact test. It considers the puzzles won with the component but lost without it, and those showing the opposite result. We make eight such comparisons per model: adding each of the four components to the map, and removing each from full context. We apply the Holm correction across these eight tests to account for multiple comparisons, and call an effect *significant* when its adjusted p-value is below 0.05. The bootstrap intervals are not adjusted for multiple comparisons, so an interval can exclude zero even when the corresponding effect is not significant under this rule.
// src: analysis/README.md; analysis/metrics.py; analysis/out/pairs.md

*Probabilities.* For Jev, Laya, GLiClass and Qwen3.5-4B, we compare the probability assigned to the chosen move with how often moves assigned similar probabilities are optimal (calibration @guo2017calibration). We report two measures. *Expected calibration error* (ECE) groups moves into ten equal-width probability ranges and compares the average probability in each group with the fraction of moves that were optimal. The absolute differences are averaged, giving more weight to groups containing more moves. The *Brier score* is the average squared difference between the chosen move's probability and its outcome: 1 if optimal, 0 otherwise. Lower values indicate closer agreement under these measures.

These measures treat the chosen option's probability as a prediction that the move is optimal. This interpretation has a limitation: several moves can be equally optimal, while the model distributes probability between them. For example, assigning 0.5 to each of two optimal moves appears underconfident under these measures, even though either choice is correct.
// src: analysis/metrics.py; analysis/out/calibration.md

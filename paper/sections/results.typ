#import "../lib.typ": todo

= Results <sec:results>

== Success rate and efficiency

DeepSeek V4.1 Flash (reasoning) wins more games than any other model, with non-overlapping intervals under both inputs. Its success rate is 80% [72, 87] with full context and 67% [57, 76] with the map alone. Each estimate uses 100 games.
// src: analysis/out/main.md; analysis/out/coverage.md

Jev wins 32% with the map alone, below the wall-aware greedy baseline's observed 37% and above random's 4%. With full context, Jev, Gemma and DeepSeek without reasoning win 57%, 61% and 60%. Paired success-rate differences for Jev minus Gemma are −3 percentage points [−11, 5] with the map and −4 [−10, 2] with full context; against DeepSeek they are −7 [−14, 0] and −3 [−11, 5]. These intervals establish no advantage for Jev, without showing equality or inferiority. Laya and GLiClass win 2% and 3% with the map, near random; full context raises them to 12% and 13%.
// src: analysis/out/main.md; analysis/out/pairs.md

#include "main_table.typ"

#figure(image("../../analysis/out/fig_main.pdf", width: 85%), placement: none,
  caption: [Compass success rate and progress with the map alone (pale) and full context (darker). Intervals resample puzzles. Each model/input uses 100 games.]) <fig:main>
// src: analysis/out/main.md; analysis/out/coverage.md

== Effects of input components

We compare the same puzzles with and without each component. For Jev, adding simulated outcomes to the map raises success rate by 16 percentage points [9, 23] and progress by 0.18 [0.13, 0.24]. Adding interaction history raises progress by 0.15 [0.11, 0.21]. Both additions pass the Holm-adjusted success-rate test. These comparisons measure improvements over the map alone; they do not establish that simulations outperform history.
// src: analysis/out/components.md

The effect depends on what else the request contains. Including history in full context adds 0.06 [0.01, 0.10] progress, whereas including simulated outcomes changes progress by 0.00 [-0.04, 0.05]. Neither corresponding success-rate contrast passes Holm correction. Several descriptions may help with the same decision.
// src: analysis/out/components.md

#figure(image("../../analysis/out/fig_components.pdf", width: 100%), placement: none,
  caption: [Paired change in success rate when a component is included. Circles compare adding it to the map alone; squares compare full context with and without it. Positive means inclusion helps. Filled markers identify McNemar tests that pass Holm correction.]) <fig:ablation>
// src: analysis/out/components.md

== Exam

#block(breakable: false)[
On the exam, DeepSeek V4.1 Flash (reasoning) reaches 94% [91, 96] optimality with full context. Jev and Gemma both reach 90% [87, 93]; their paired difference is 0 percentage points [−1, 2]. DeepSeek without reasoning reaches 86% [83, 90], with a Jev-minus-DeepSeek paired difference of 4 points [1, 6]. Full context improves optimality for every model: 16 points for Jev, 21 for Laya and GLiClass, 20 for Gemma, 30 for Qwen3.5-4B, 19 for DeepSeek without reasoning and 5 for DeepSeek V4.1 Flash (reasoning). All paired input-effect intervals exclude zero.
// src: analysis/out/exam.md; analysis/out/exam_inputs.md; analysis/out/pairs.md

With full context, Jev is 90% optimal on shared exam positions, 79% optimal in its own games after equal puzzle weighting, and has 57% game success. With the map alone, its exam optimality is 74% and its equally weighted game optimality is 38%. Accuracy across all moves made during the model's games is 16% with the map and 64% with full context. Weighting explains part of the gap. Jev's full-context start and late-route exam scores are 86% and 97%; the positions differ in more than history.
// src: analysis/out/exam.md
]

#figure(image("../../analysis/out/fig_exam.pdf", width: 70%), placement: auto,
  caption: [Optimality on the same 495 exam items. Pale and dark bars show map alone and full context; intervals resample puzzles. Diamonds show own-game optimality averaged within puzzles and then equally over puzzles, matching exam weighting. Baselines have one bar.]) <fig:exam>
// src: analysis/out/exam.md

== Blocked moves and progress

With the map alone, 82% of Jev's moves leave the board unchanged. Without history, a blocked move leaves the board and its description unchanged, and only the option order changes, so Jev can choose the same move into the same wall again. With full context, the unchanged-board share is 0.4%, yet 43% of games still fail. Final-state progress is 0.65, below progress of 0.68. The distinction matters more for Qwen3.5-4B: its full-context scores are 0.56 and 0.66. A game can approach the goal and then finish farther away.
// src: analysis/out/main.md

== Success rate by level

At levels 12, 15, 20, Jev's full-context success rates are 20%, 10%, 0%. Each level contains ten puzzles. DeepSeek V4.1 Flash (reasoning) wins 70%, 40% and 30% at those levels with full context, compared with 50%, 20% and 20% with the map alone. The higher levels remain difficult even with reasoning. These rates describe the generated levels.
// src: analysis/out/levels.md

#figure(image("../../analysis/out/fig_levels.pdf", width: 100%), placement: none,
  caption: [Compass success rate by categorical level with the map alone and full context. Labels give shortest-route distance in compass steps; horizontal gaps do not represent distance differences. Levels 1 and 2 have five puzzles each; others ten.]) <fig:levels>
// src: analysis/out/levels.md

== Action spaces

For Jev with the map alone, success rate is 32% under `compass`, 40% under `two-moves`, 47% under `three-moves` and 26% under `up-to-three-moves`. With full context, `compass` and `up-to-three-moves` give 57% and 49%; Gemma wins 61% under both. Longer sequences do not consistently improve success rate. Option count and text length also change.
// src: analysis/out/action_spaces.md

#figure(image("../../analysis/out/fig_action_spaces.pdf", width: 100%), placement: none,
  caption: [Success rate across `compass`, `two-moves`, `up-to-two-moves`, `three-moves` and `up-to-three-moves` (4, 16, 20, 64 and 84 options). Step count and observation interval also change. Qwen3.5-4B and both DeepSeek configurations ran compass moves only. Random is the same in both panels.]) <fig:rules>
// src: analysis/out/action_spaces.md

== Probability analysis

Across compass conditions, Jev's selected-option probabilities exceed its observed optimality on its own trajectories: mean probability is 0.719, while 51% of chosen moves are optimal. Its ECE is 0.209 and binary Brier score 0.283 over 14,642 moves. A predictor that always reports the observed optimal-move frequency scores 0.250, an in-sample reference. Laya's ECE is 0.133 with 17.5% optimality; Qwen3.5-4B's is 0.064 with 47.5% optimality. Low calibration error does not establish effective navigation. These scores test whether selected-option probability predicts solver-optimality on each model's own trajectories across ten inputs. They are an operational confidence diagnostic, not a complete test of the action distribution. On common exam questions, Jev's ECE is 0.063 with the map and 0.059 with full context.
// src: analysis/out/calibration.md; analysis/out/exam.md

TypeSafe defines Choice confidence as $c = (p_(max) - 1/n) / (1 - 1/n)$ @typesafeconfidence. Across Jev's 14,642 compass moves, the maximum discrepancy from this formula is 0.023 and remains unexplained. For a fixed option count, the formula ranks moves exactly as the top probability does; it defines a rescaled score, rather than an independent correctness prediction.
// src: analysis/out/calibration.md; paper/references.bib

#figure(image("../../analysis/out/fig_calibration.pdf", width: 60%), placement: auto,
  caption: [Reliability pooling all compass conditions; only bins with at least 30 moves are shown. Points compare mean chosen-move probability with optimality, accepting ties. The diagonal indicates agreement. Gemma and DeepSeek supply no option probabilities.]) <fig:reliability>
// src: analysis/out/calibration.md

== Cost and latency

These estimates pool all compass conditions. Median latency measures the successful answering call alone, excluding retries, waits and model loading: 0.503 seconds for Jev, 0.653 for Gemma, 0.805 for DeepSeek without reasoning and 6.817 for DeepSeek V4.1 Flash (reasoning). Recorded cost per 100 games is \$0.059, \$0.047 and \$0.348 for the three chat configurations, respectively. Dollar costs are unavailable for Jev and local models. Different services and hardware limit comparisons; @app:reproducibility records the setup and accounting boundaries.
// src: analysis/out/cost.md; src/system_one_control/players/remote.py; src/system_one_control/players/local.py

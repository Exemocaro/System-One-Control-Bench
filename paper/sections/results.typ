#import "../lib.typ": todo

= Results <sec:results>

== Completion and efficiency

#include "main_table.typ"

DeepSeek V4.1 Flash with capped reasoning wins substantially more games than any other model. Its won rate is 80% [72, 87] with full context and 67% [57, 76] with the map alone. Each estimate uses 100 games. All ten reasoning conditions have been evaluated, with no recorded errors.
// src: analysis/out/main.md; analysis/out/coverage.md

Jev wins 32% with the map alone, below the wall-aware greedy baseline's observed 37% and above random's 4%. With full context, Jev, Gemma and DeepSeek without reasoning win 57%, 61% and 60%, respectively. Their intervals overlap. We describe these observed rates as similar without claiming that the models perform equally. Laya and GLiClass win 2% and 3% with the map alone, close to random. Full context raises their rates to 12% and 13%, but completion remains low.
// src: analysis/out/main.md

#figure(image("../../analysis/out/fig_main.pdf", width: 85%), placement: top,
  caption: [Compass won rate and progress with the map alone (pale) and full context (darker). Intervals resample puzzles. Each model/input uses 100 games.]) <fig:main>
// src: analysis/out/main.md; analysis/out/coverage.md

== Effects of input components

We compare the same puzzles with and without each component. For Jev, adding simulated outcomes to the map raises won rate by 16 percentage points [9, 23] and progress by 0.18 [0.13, 0.24]. Adding interaction history raises progress by 0.15 [0.11, 0.21]. Both additions pass the Holm-adjusted won-rate test. These comparisons measure improvements over the map alone; they do not establish that simulations outperform history.
// src: analysis/out/components.md

The effect depends on what else the request contains. Including history in full context adds 0.06 [0.01, 0.10] progress, whereas including simulated outcomes changes progress by 0.00 [-0.04, 0.05]. Neither corresponding won-rate contrast passes Holm correction. Our interpretation is that several descriptions may help with the same decision, so a component's benefit alone need not mean it is needed with the others present.
// src: analysis/out/components.md

#figure(image("../../analysis/out/fig_components.pdf", width: 100%), placement: top,
  caption: [Paired change in won rate when a component is included. Circles compare adding it to the map alone; squares compare full context with and without it. Positive means inclusion helps. Filled markers identify McNemar tests that pass Holm correction.]) <fig:ablation>
// src: analysis/out/components.md

== Action spaces

For Jev with the map alone, won rate is 32% with compass moves, 40% with two-step sequences and 47% with three-step sequences. It falls to 26% when sequences of up to three steps are offered. With full context, the corresponding compass and up-to-three-step rates are 57% and 49%. Gemma's full-context rate is 61% under both formulations. Longer sequences therefore do not consistently improve completion. Each formulation also changes the number of options and the amount of text, so these results cannot be attributed to option count alone.
// src: analysis/out/action_spaces.md

#figure(image("../../analysis/out/fig_action_spaces.pdf", width: 100%), placement: top,
  caption: [Won rate with the map alone and full context across compass, two-step, up-to-two-step, three-step and up-to-three-step moves. Their option counts are 4, 16, 20, 64 and 84. More steps are executed before the next observation as well as more options being offered.]) <fig:rules>
// src: analysis/out/action_spaces.md

== Fixed-state evaluation

The planned shared-position experiment will ask every model the same compass questions with the map alone and with full context. It will complement complete games, where different models may encounter very different positions. #todo[fixed-state evaluation results]

== Blocked moves and progress

With the map alone, 82% of Jev's moves leave the board unchanged. With full context, that share is 0.4%. This reduction accompanies better completion, but does not by itself establish better route planning. Final-state progress is 0.649, below its closest-state progress of 0.68. The distinction matters more for Qwen: its full-context scores are 0.560 and 0.66. A game can approach the goal and then finish farther away.
// src: analysis/out/main.md

== Completion by level

At levels 12, 15, 20, Jev's full-context won rates are 20%, 10%, 0%. Each level contains ten puzzles. Capped reasoning wins 70%, 40% and 30% at those levels with full context, compared with 50%, 20% and 20% with the map alone. The higher levels remain difficult even with reasoning. These rates describe the generated levels, which vary in layout as well as shortest-route length; they do not isolate the effect of distance.
// src: analysis/out/levels.md

#figure(image("../../analysis/out/fig_levels.pdf", width: 100%), placement: top,
  caption: [Compass won rate by level with the map alone and full context. Level is shortest-route distance in compass steps. Levels 1 and 2 have five puzzles each; every other level has ten.]) <fig:levels>
// src: analysis/out/levels.md

== Probability analysis

We pool all compass conditions and ask whether the chosen move was optimal. Jev assigns its chosen move a mean probability of 0.719, while 51% of those moves are optimal. Its ECE is 0.209 and binary Brier score 0.283 over 14,642 moves. Laya's ECE is 0.133 with 17.5% optimality; Qwen's is 0.064 with 47.5% optimality. Low calibration error alone does not establish effective navigation. The models also reach different positions, so these scores are not comparisons on a shared set of questions.
// src: analysis/out/calibration.md

TypeSafe defines Choice confidence as $c = (p_(max) - 1/n) / (1 - 1/n)$ @typesafeconfidence. On all 14,642 Jev compass moves, the reported confidence differs from $(p_(max) - 1/n) / (1 - 1/n)$ by at most 0.023. For a fixed number of options, the formula ranks moves exactly as the top probability does. Reported confidence is therefore a rescaled score rather than an independent prediction of correctness.
// src: analysis/out/calibration.md (move count); TypeSafe confidence documentation; recorded confidence-formula check

#figure(image("../../analysis/out/fig_calibration.pdf", width: 60%), placement: top,
  caption: [Reliability after pooling all compass conditions. Each point compares mean chosen-move probability with the fraction of those moves that are optimal, accepting any tied best move. The diagonal indicates agreement between probability and observed optimality.]) <fig:reliability>
// src: analysis/out/calibration.md

== Cost and latency

The tables pool all compass conditions. Median inference time is 0.503 seconds for Jev, 0.653 for Gemma, and 0.805 for DeepSeek without reasoning. Capped reasoning takes 6.817 seconds. Recorded cost per 100 games is \$0.059, \$0.047 and \$0.348, respectively. Dollar costs are unavailable for Jev and the local models. These timings compare the evaluated services and hardware, not controlled implementations on the same machine.
// src: analysis/out/cost.md

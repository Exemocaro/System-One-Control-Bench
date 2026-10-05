#import "../lib.typ": todo

= Results <sec:results>

== Games won

DeepSeek V4.1 Flash (reasoning) wins the most games: 80% [72, 87] with full context and 67% [57, 76] with the map only (@tab:main, @fig:main). With the same input, its intervals do not overlap those of any other model.
// src: analysis/out/main.md

With full context, Jev, Gemma 4 26B and DeepSeek V4.1 Flash win 57%, 61% and 60% of games. Compared puzzle by puzzle, Jev wins 4 percentage points fewer than Gemma [−10, 2] and 3 fewer than DeepSeek [−11, 5]. Both intervals include zero, so the data cannot tell these three models apart. With the map only, Jev wins 32%, between Random (4%) and Greedy (walls) (37%). Laya and GLiClass win 2% and 3% with the map only, no better than Random, and 12% and 13% with full context. With the map only, their progress (0.10) is even below Random's (0.25). Qwen3.5-4B wins 14% and 45%.
// src: analysis/out/main.md; analysis/out/pairs.md

#include "main_table.typ"

#figure(image("../../analysis/out/fig_main.pdf", width: 85%), placement: none,
  caption: [Success rate and progress under compass rules, with the map only (pale bars) and full context (dark bars). Lines show 95% intervals.]) <fig:main>
// src: analysis/out/main.md

== What each component adds

@fig:ablation shows how each model's success rate changes when a component is included. Added to map only, move outcomes help most models: Jev gains 16 percentage points [9, 23], and the gain is significant for Jev, Laya, GLiClass, Gemma 4 26B and Qwen3.5-4B. For Jev, surroundings (+13 points) and move history (+14) also help significantly. The subgoal helps least (+5 for Jev, not significant).
// src: analysis/out/components.md

Removing a single component from full context changes little. For Jev none of the four removals is significant, and the largest change in progress is 0.06 [0.01, 0.10], for move history. Across all models, only one removal is significant: without move outcomes, Gemma 4 26B wins 10 points fewer [4, 17]. The components seem to overlap, so that the others can make up for a missing one. @app:components gives every number.
// src: analysis/out/components.md

#figure(image("../../analysis/out/fig_components.pdf", width: 100%), placement: none,
  caption: [Change in success rate when a component is included (compass rules), with 95% intervals. Circles: map + component compared with map only. Squares: full context compared with full context minus the component. Right of the vertical line, the component helps. Filled markers are significant (McNemar's test, Holm-corrected).]) <fig:ablation>
// src: analysis/out/components.md

== Exam versus games

With full context, Jev answers 90% [87, 93] of the exam positions optimally (@tab:exam). This equals Gemma 4 26B (paired difference 0 points [−1, 2]) and is 4 points [1, 6] above DeepSeek V4.1 Flash. Only DeepSeek V4.1 Flash (reasoning) scores higher, at 94% [91, 96]. Full context raises every model's exam score, from 5 points for DeepSeek V4.1 Flash (reasoning) to 30 points for Qwen3.5-4B; every one of these gains has an interval above zero.
// src: analysis/out/exam.md; analysis/out/exam_inputs.md; analysis/out/pairs.md

Good exam answers do not translate into won games. Jev answers 90% of the exam positions optimally but wins only 57% of its games, and in those games 79% of its moves are optimal on average. If every move is counted equally, instead of averaging per game, the share drops to 64%, because lost games are long and full of mistakes. A baseline shows the gap most clearly: Greedy (walls), which never plans, answers 89% of the exam positions optimally but wins only 37% of its games. In most positions, heading straight for the target is optimal. The few positions that need a detour decide the game.
// src: analysis/out/exam.md

#include "exam_table.typ"

== Blocked moves

With the map only, 82% of Jev's moves are blocked. Without the move history, a blocked move leaves the request unchanged apart from the order of the options, so Jev can choose the same move into the same wall again, and often does. With full context only 0.4% of its moves are blocked, yet it still loses 43% of its games: avoiding walls is only part of finding the way. Some games get close to the goal and then wander off. With full context, Qwen3.5-4B's progress is 0.66, but its final-state progress is 0.56.
// src: analysis/out/main.md

== Success by level

Success falls as the level rises (@fig:levels). At levels 12, 15 and 20, which have ten puzzles each, Jev wins 20%, 10% and 0% of games with full context. DeepSeek V4.1 Flash (reasoning) wins 70%, 40% and 30% with full context, and 50%, 20% and 20% with the map only. Long routes stay hard even with reasoning.
// src: analysis/out/levels.md

#figure(image("../../analysis/out/fig_levels.pdf", width: 100%), placement: none,
  caption: [Success rate by level under compass rules. The level is the length of the shortest route in steps; levels are evenly spaced on the axis whatever their value. Levels 1 and 2 have five puzzles each, the others ten.]) <fig:levels>
// src: analysis/out/levels.md

== Move rules

Longer moves have mixed effects (@fig:rules). For Jev with the map only, success rises from 32% under `compass` to 40% under `two-moves` and 47% under `three-moves`, but falls to 26% under `up-to-three-moves`, the rules with the most options (84). With full context, Jev and Gemma 4 26B stay within 8 points of their compass results under every rule. Qwen3.5-4B changes most: with full context its success rate rises from 45% under `compass` to 70% under `two-moves` and 61% under `up-to-two-moves`, but with the map only it falls from 14% to 3% and 11%. Laya and GLiClass stay below 15% under every rule. Because the number of options, the length of their texts and the steps between looks at the board all change together, we cannot say which of them causes these effects.
// src: analysis/out/action_spaces.md

#figure(image("../../analysis/out/fig_action_spaces.pdf", width: 100%), placement: none,
  caption: [Success rate under the five move rules (options per move in brackets). Qwen3.5-4B played `compass`, `two-moves` and `up-to-two-moves`; DeepSeek played compass only. Baselines ignore the input, so their lines are the same in both panels.]) <fig:rules>
// src: analysis/out/action_spaces.md

== Probabilities

Jev is overconfident (@fig:reliability). Over all 14,642 of its compass moves, under all ten inputs, it gives the chosen move an average probability of 0.72, but only 51% of those moves are optimal; its ECE is 0.21. Its Brier score, 0.283, is worse than the 0.250 it would get by giving every move the same probability, 0.51. Its probabilities still carry some signal: moves chosen with a probability of 0.9 or more are optimal 74% of the time, against 42% for the rest. On the exam, Jev is well calibrated (ECE 0.06 with either input), so its overconfidence shows up in the positions its own games lead to.
// src: analysis/out/calibration.md; analysis/out/exam.md; analysis/out/hypotheses.md

Laya and Qwen3.5-4B are better calibrated (ECE 0.13 and 0.06) and GLiClass worse (0.33). Good calibration does not mean good play: only 17.5% of Laya's chosen moves are optimal, and its low probabilities say so. Jev also returns a confidence score. On every move it equals, to within 0.023, the top probability rescaled so that 0 means all options are equally likely and 1 means certainty, $(p_"max" - 1 slash n) slash (1 - 1 slash n)$ for $n$ options @typesafeconfidence. It therefore adds no information of its own.
// src: analysis/out/calibration.md; paper/references.bib

#figure(image("../../analysis/out/fig_calibration.pdf", width: 60%), placement: auto,
  caption: [Calibration over all compass games. Moves are grouped by the probability of the chosen move; each point compares a group's average probability with the share of its moves that were optimal. Points on the dotted diagonal are perfectly calibrated, and points below it are overconfident. Only groups of at least 30 moves are shown. Gemma and DeepSeek give no probabilities.]) <fig:reliability>
// src: analysis/out/calibration.md

== Cost and speed

Median time per answer, counting only the successful call, is 0.50 seconds for Jev, 0.65 for Gemma 4 26B, 0.81 for DeepSeek V4.1 Flash and 6.8 for DeepSeek V4.1 Flash (reasoning). Qwen3.5-4B takes 0.23 seconds on the laptop's GPU. Laya and GLiClass, whose compass games ran on a CPU, take about 1.8 seconds. The recorded cost per 100 compass games is \$0.059 for Gemma, \$0.047 for DeepSeek V4.1 Flash and \$0.348 for DeepSeek V4.1 Flash (reasoning). We have no dollar costs for Jev or the local models. Services and hardware differ, so these numbers are only a rough guide (@app:reproducibility).
// src: analysis/out/cost.md

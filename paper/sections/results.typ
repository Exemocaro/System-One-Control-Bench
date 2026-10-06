#import "../lib.typ": todo

= Results <sec:results>

Numbers in brackets are 95% intervals (@sec:statistics). For a single score they give the range it would likely take on another set of similar puzzles; for a difference between two models or conditions, an interval that includes 0 means the data do not show which is better.

== Games won

DeepSeek V4.1 Flash (reasoning) wins the most games: 80% [72, 87] with full context and 67% [57, 76] with the map only (@tab:main, @fig:main). Under the same condition, its intervals do not overlap those of any other model.
// src: analysis/out/main.md

With full context, Jev, Gemma 4 26B and DeepSeek V4.1 Flash win 57%, 61% and 60% of games. Compared puzzle by puzzle, Jev wins 4 percentage points fewer than Gemma 4 26B [−10, 2] and 3 fewer than DeepSeek V4.1 Flash [−11, 5]. Both intervals include zero, so neither comparison shows a difference in success rate between Jev and the chat model. With the map only, Jev wins 32%, between Random (4%) and Greedy (walls) (37%). Laya and GLiClass win 2% and 3% with the map only, no better than Random, and 12% and 13% with full context. With the map only, their progress (0.10) is even below Random's (0.25). Qwen3.5-4B wins 14% with the map only and 45% with full context.
// src: analysis/out/main.md; analysis/out/pairs.md

#include "main_table.typ"

#figure(image("../../analysis/out/fig_main.pdf", width: 85%), placement: none,
  caption: [Success rate and progress under compass rules, with the map only (pale bars) and full context (dark bars). Baselines do not read the request and have a single bar. Lines show 95% intervals.]) <fig:main>
// src: analysis/out/main.md

== What each component adds

@fig:ablation shows how each model's success rate changes when a component is included. Added to map only, move outcomes help most models: Jev gains 16 percentage points [9, 23], and the gain is significant for Jev, Laya, GLiClass, Gemma 4 26B and Qwen3.5-4B. For Jev, surroundings (+13 points) and move history (+14) also help significantly. The subgoal helps least (+5 for Jev, not significant).
// src: analysis/out/components.md

Removing a single component from full context rarely makes a clear difference. For Jev none of the four removals is significant, and the largest change in progress is 0.06 [0.01, 0.10], for move history. Across all models, only one removal is significant: without move outcomes, Gemma 4 26B wins 10 points fewer [4, 17]. A few other changes, up to 11 points, have intervals that exclude zero but are not significant once corrected for the number of tests. The components seem to overlap, so that the others can make up for a missing one. @app:components reports all component effects.
// src: analysis/out/components.md

#figure(image("../../analysis/out/fig_components.pdf", width: 100%), placement: auto,
  caption: [Change in success rate when a component is included (compass rules). Circles: map + component compared with map only. Squares: full context compared with full context minus the component. Right of the vertical line, the component helps. Each line is a 95% interval: where it crosses the vertical line, the data do not show whether the component helps or hurts. Filled markers are significant (McNemar's test, Holm-corrected; @sec:statistics).]) <fig:ablation>
// src: analysis/out/components.md

== Exam versus games

With full context, Jev answers 90% [87, 93] of the exam positions optimally (@tab:exam). This matches Gemma 4 26B's rounded score (paired difference 0 points [−1, 2]) and is 4 points [1, 6] above DeepSeek V4.1 Flash. Only DeepSeek V4.1 Flash (reasoning) scores higher, at 94% [91, 96]. Full context raises every model's exam score, from 5 points for DeepSeek V4.1 Flash (reasoning) to 30 points for Qwen3.5-4B; every one of these gains has an interval above zero.
// src: analysis/out/exam.md; analysis/out/exam_inputs.md; analysis/out/pairs.md

A high exam score does not guarantee a high success rate. Jev answers 90% of the exam positions optimally but wins only 57% of its games, and in those games 79% of its moves are optimal on average. If every move is counted equally, instead of averaging per game, the share drops to 64%, because lost games are long and full of mistakes. A baseline shows the gap most clearly: Greedy (walls), which never plans, answers 89% of the exam positions optimally but wins only 37% of its games. In most positions, heading straight for the target is optimal. The few positions that need a detour probably decide many games.
// src: analysis/out/exam.md

#include "exam_table.typ"

== Blocked moves

Under compass rules with the map only, most models walk into walls often: 82% of Jev's moves are blocked, and 52% to 85% of the other models' moves, except DeepSeek V4.1 Flash (reasoning) at 14%. Without the move history, a blocked move leaves the request unchanged apart from the order of the options, so a model can choose the same move into the same wall again, and they often do. Full context cuts blocked moves to 0.4% for Jev, 2% for DeepSeek V4.1 Flash (reasoning), 4% for Gemma 4 26B, 6% for Qwen3.5-4B and 10% for DeepSeek V4.1 Flash, but Laya and GLiClass still walk into walls on 53% and 69% of their moves. Avoiding walls is only part of finding the way: with 0.4% blocked moves, Jev still loses 43% of its games.
// src: analysis/out/main.md

Some games get close to the goal and then drift away again. Progress counts the closest point a game reached, and final-state progress the point where it ended, so the gap between the two shows how far games drift back. With full context the gap is 0.03 to 0.05 for most models, but 0.10 for Qwen3.5-4B (0.66 against 0.56) and 0.11 for Laya (0.26 against 0.15).
// src: analysis/out/main.md

== Success by level

Success falls as the level rises (@fig:levels). Greedy (walls), which heads straight for its next target, loses every puzzle from level 10 up, where the route needs longer detours. At levels 12, 15 and 20, which have ten puzzles each, Jev wins 20%, 10% and 0% of games with full context. DeepSeek V4.1 Flash (reasoning) wins 70%, 40% and 30% with full context, and 50%, 20% and 20% with the map only. Long routes stay hard even with reasoning.
// src: analysis/out/levels.md

#figure(image("../../analysis/out/fig_levels.pdf", width: 100%), placement: auto,
  caption: [Success rate by level under compass rules. Levels are evenly spaced on the axis whatever their value.]) <fig:levels>
// src: analysis/out/levels.md

== Move rules

Longer moves help some models and hurt others (@fig:rules). The success rates under `compass`, `two-moves`, `up-to-two-moves`, `three-moves` and `up-to-three-moves`, in that order, are:

- *Jev:* with full context 57%, 63%, 57%, 63% and 49%; with the map only 32%, 40%, 39%, 47% and 26%. Fixed-length sequences help a little, and `up-to-three-moves`, the rules with the most options (84), is the worst under both conditions.
- *Gemma 4 26B:* with full context 61%, 68%, 63%, 69% and 61%; with the map only 35%, 44%, 43%, 33% and 32%. With full context every sequence rule does at least as well as `compass`.
- *Qwen3.5-4B:* with full context 45%, 70%, 61%, 71% and 58%, the largest gains of any model; with the map only 14%, 3%, 11%, 10% and 9%, all below `compass`. Its gains depend on the move outcomes: under the two three-step rules, full context without them wins only 16% and 18%.
- *Laya:* with full context 12%, 7%, 9%, 13% and 5%; with the map only 2% to 7% under every rule.
- *GLiClass:* with full context 13%, 6%, 3%, 6% and 4%; with the map only 1% to 4% under every rule. Its best full-context result is under `compass`.
- *DeepSeek V4.1 Flash* (both setups) played compass rules only.

These differences between rules were not tested puzzle by puzzle, and for most of them the 95% intervals overlap. Because the number of options, the length of their texts and the steps before the model sees the board again all change together, we cannot say which of them causes these effects.
// src: analysis/out/action_spaces.md; benchmarks/2026-10-06_08-32_qwen3.5-4b_all_three-moves.txt; benchmarks/2026-10-06_10-25_qwen3.5-4b_all_up-to-three-moves.txt

#figure(image("../../analysis/out/fig_action_spaces.pdf", width: 100%), placement: auto,
  caption: [Success rate under the five move rules (options per move in brackets). Both DeepSeek V4.1 Flash setups played compass only and are not shown.]) <fig:rules>
// src: analysis/out/action_spaces.md

== Probabilities

Jev, Laya, GLiClass and Qwen3.5-4B return a probability for every option. In their own compass games, under all ten conditions (@fig:reliability):

- *Jev* gives its chosen moves higher probabilities than how often they are optimal. Over its 14,642 moves, the chosen move gets an average probability of 0.72, but only 51% of those moves are optimal; its ECE is 0.21. Its Brier score, 0.283, is worse than the 0.250 it would get by always giving the chosen move a probability of 0.51, its share of optimal moves in the same data. Its probabilities still carry some signal: moves chosen with a probability of 0.9 or more are optimal 74% of the time, against 42% for the rest. On the exam the same measure gives a much lower ECE of 0.06 under either condition, so the gap shows up mainly in the positions its own games lead to.
- *Laya* gives its chosen moves low probabilities (0.31 on average), and only 17.5% of them are optimal. Its ECE is 0.13, but its Brier score (0.166) is still worse than a constant guess (0.144): a low ECE does not mean good play.
- *GLiClass* has the highest ECE, 0.33: its chosen moves get 0.45 on average, but only 12% are optimal. Its Brier score (0.220) is twice that of a constant guess (0.107).
- *Qwen3.5-4B* matches its probabilities best: ECE 0.06, with an average probability of 0.54 and 48% of chosen moves optimal. It is the only one of the four whose Brier score (0.232) beats a constant guess (0.249).

Jev also returns a confidence score. On every move it equals, to within 0.023, the top probability rescaled so that 0 means all options are equally likely and 1 means certainty, $(p_"max" - 1 slash n) slash (1 - 1 slash n)$ for $n$ options @typesafeconfidence. So it adds almost nothing to the probabilities; we cannot explain the small differences.
// src: analysis/out/calibration.md; analysis/out/exam.md; analysis/out/hypotheses.md; paper/references.bib

#figure(image("../../analysis/out/fig_calibration.pdf", width: 48%), placement: none,
  caption: [Calibration over all compass games. Moves are grouped by the probability of the chosen move; each point compares a group's average probability with the share of its moves that were optimal. Points on the dotted diagonal are perfectly calibrated, and points below it are overconfident. Only groups of at least 30 moves are shown, so Laya, which rarely gives a probability above 0.5, has only three points. Gemma 4 26B and the DeepSeek V4.1 Flash setups give no probabilities.]) <fig:reliability>
// src: analysis/out/calibration.md

== Cost and speed

Median time per answer, counting only the successful call, is 0.50 seconds for Jev, 0.65 for Gemma 4 26B, 0.81 for DeepSeek V4.1 Flash and 6.8 for DeepSeek V4.1 Flash (reasoning). Qwen3.5-4B takes 0.23 seconds on a laptop GPU (@app:reproducibility). Laya and GLiClass, whose compass games ran on a CPU, take about 1.8 seconds. The recorded cost per 100 compass games is \$0.059 for Gemma 4 26B, \$0.047 for DeepSeek V4.1 Flash and \$0.348 for DeepSeek V4.1 Flash (reasoning). We have no dollar costs for Jev or the local models. Services and hardware differ, so these numbers are only a rough guide (@app:reproducibility).
// src: analysis/out/cost.md

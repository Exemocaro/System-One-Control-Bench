#import "../lib.typ": todo

= Discussion and limitations <sec:limitations>

With full context, Jev is 90% optimal on shared exam positions, 79% optimal in its own games after equal puzzle weighting, and completes 57% of games. Ten independent 90%-accurate decisions would all be right about 35% of the time. This is not a prediction: errors can be recovered, routes differ in length, and decisions are not independent. Games expose states reached by each model rather than scripted exam positions. Actions change later state distributions @ross2011; this is conceptual background, not a test of that method. We did not isolate the cause of the exam/game gap. Long failed games dominate pooled accuracy and probability diagnostics. Start and late-route exam positions also differ in distance and inventory, so their contrast cannot isolate history's effect.
// src: analysis/out/exam.md; analysis/out/main.md

Full context nearly removes unchanged-board moves, yet 43% of games still fail. Avoiding blocked answers is only part of navigation. Explicit transitions may help, but wording and text length are not controlled separately. Comparisons that remove one component from full context do not show that any component is needed with the others present.
// src: analysis/out/main.md; analysis/out/components.md

Sequence actions change option count, text length, observation frequency and outcome duplication. Fixed-length subgoal prompts say "shortest path"; up-to prompts say "the fewest turns." Both are evaluated by decision count. Rounding also changes the attempted-step budget: a four-step puzzle allows four three-step moves (up to twelve steps), versus eight compass moves. These effects cannot be isolated. Levels vary in layout and route length; level effects do not isolate distance.
// src: src/system_one_control/world.py; src/system_one_control/prompts.py; analysis/out/levels.md

We test one symbolic world with five or ten puzzles per level, without a held-out set. Prompts preceded puzzles. Results are single trajectories: repeated calls changed Jev's probabilities and chat answers; reruns would play different games (@app:reproducibility). Provider changes, inference caps and input limits matter. Laya ran outside its training tasks. Hardware differs; missing costs limit price comparisons.
// src: analysis/out/cost.md; analysis/out/coverage.md; paper/references.bib; analysis/manifest.toml

#include "leaderboard.typ"

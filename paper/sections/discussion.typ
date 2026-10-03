#import "../lib.typ": todo

= Discussion and limitations <sec:limitations>

Capped reasoning has the highest completion rate and longer median latency. Jev's full-context won rate overlaps those of the two chat models without reasoning, indicating similar observed performance without establishing equality.
// src: analysis/out/main.md; analysis/out/cost.md

For Jev, local descriptions, history and simulated outcomes improve completion when added to the map alone; the subgoal does not pass the corrected test. Full context reduces blocked moves. Explicit transitions may make the map easier to use, but wording and text length are not controlled separately. The comparisons do not identify how the model reasons internally, and removal contrasts do not show that any component is needed with the others present.
// src: analysis/out/main.md; analysis/out/components.md

Sequence moves change option count, text length, observation frequency and how many options reach the same position; we cannot isolate their effects. Failed games can contribute many repeated decisions, so pooled calibration reflects each model's encountered positions. On common exam questions, Jev and Gemma both have observed full-context optimality of 90% [87, 93], exceeding their own-game optimality.
// src: analysis/out/exam.md; analysis/out/action_spaces.md; analysis/out/calibration.md

The scope is one symbolic world, with five or ten puzzles per level and no separate held-out set. Prompts preceded puzzle generation. One trajectory per game does not measure repeated-call variation. Provider changes, inference caps and input limits can affect performance; Laya was evaluated outside its training tasks. Chat endpoints supply no option distributions. Timings use different services and hardware, and missing dollar costs limit price comparisons.
// src: analysis/out/levels.md; analysis/out/cost.md; analysis/out/coverage.md; Laya model card; prompt history

#include "leaderboard.typ"

#import "../lib.typ": todo

= Discussion and limitations <sec:limitations>

Full context nearly removes Jev's unchanged-board moves, yet 43% of games still fail. Avoiding a repeated blocked answer is only one part of navigating a route. Explicit transitions may make the map easier to use, but wording and text length are not controlled separately. Removal contrasts do not show that any component is needed with the others present, and these comparisons do not identify how the model reasons internally.
// src: analysis/out/main.md; analysis/out/components.md

The exam/game gap remains after equal puzzle weighting: models can answer scripted individual decisions well and still fail to sustain a route. The exam samples scripted positions, while games expose the states reached by each model. Failed games also contribute repeated decisions, so pooled calibration depends on trajectories. Sequence moves change option count, text length, observation frequency and outcome duplication together; their effects cannot be isolated here.
// src: analysis/out/exam.md; analysis/out/action_spaces.md; analysis/out/calibration.md

The scope is one symbolic world, with five or ten puzzles per level and no separate held-out set. Prompts preceded puzzle generation. One trajectory per game does not measure repeated-call variation. Provider changes, inference caps and input limits can affect performance; Laya was evaluated outside its training tasks. Chat endpoints supply no option distributions. Timings use different services and hardware, and missing dollar costs limit price comparisons.
// src: analysis/out/levels.md; analysis/out/cost.md; analysis/out/coverage.md; paper/references.bib; analysis/manifest.toml

#include "leaderboard.typ"

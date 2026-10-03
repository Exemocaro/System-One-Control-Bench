#import "../lib.typ": todo

= Discussion and limitations <sec:limitations>

Capped reasoning produces the strongest completion rates in this evaluation. Its longer median latency shows that completion and speed involve a tradeoff in this setting. Jev's full-context won rate sits within overlapping intervals with the two chat models evaluated without reasoning. This is evidence of similar observed performance, not a test that establishes equality.
// src: analysis/out/main.md; analysis/out/cost.md; analysis/out/coverage.md

For Jev, descriptions calculated from the map improve completion and greatly reduce blocked moves. One interpretation is that explicit transitions make the map easier to use. The study does not separate that explanation from wording or text length, and it does not identify how the model reasons internally. The addition and removal contrasts also differ: information that helps when supplied alone may add little once other descriptions are present.
// src: analysis/out/main.md; analysis/out/components.md

Sequence moves change several things at once: the number of options, the text describing them, how many steps execute before the next observation, and how many options lead to the same position. The current comparisons cannot identify which change causes a performance difference. Similarly, models that fail can contribute many repeated decisions, while successful games stop early. Pooled calibration therefore measures the decisions each model encountered. The fixed-state experiment will complement these results with questions shared by all models.
// src: analysis/out/action_spaces.md; analysis/out/calibration.md

The scope is one small symbolic world. The higher-level results remain limited, and only five or ten puzzles represent each level. There is no separate held-out puzzle set, although prompts were developed before the published puzzles were generated. One saved trajectory per game does not measure repeated-call variation. Provider changes, inference caps and input limits can affect performance. Laya's result concerns the evaluated specialist checkpoint outside its training tasks. Chat endpoints supply no option distributions, and the latency comparisons use different services and hardware. Missing dollar costs prevent a complete price comparison.
// src: analysis/out/levels.md; analysis/out/cost.md; analysis/out/coverage.md; Laya model card; prompt history

#include "leaderboard.typ"

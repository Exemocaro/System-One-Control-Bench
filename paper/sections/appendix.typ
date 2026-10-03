#import "../lib.typ": todo

= One complete example request <app:prompts>

This is the compass, full-context request for @fig:example, with every field and all state text retained. Lines wrap only where needed to fit the page. All 50 frozen requests are in the repository's `examples/` directory.
// src: examples/everything.json

#include "example_request.typ"

#pagebreak()
= Hypotheses specified before the main evaluation <app:hypotheses>

These hypotheses were specified before the main evaluation. The table reproduces their statements, results and verdicts from the current analysis.
// src: analysis/out/hypotheses.md

#include "hypothesis_table.typ"

= Prompt history <app:history>

Prompts were developed by inspecting a few games on one or two puzzles at a few levels before generating the benchmark puzzles. Compass text is unchanged since `35408d3` (23 September 2026, 20:10), before Jev's reported results in `9b6d9dd` (22:01) and `f23d6af` (23:48). Sequence rules entered in `a6504d7` (24 September, 00:36); their two-/three-step prompts were fixed in `b4cbdc4` (11:43), before runs at 13:41 committed in `54c1131` (14:12). Times are local, UTC+02:00. On 26 September the up-to-subgoal question was corrected to ask for the route taking the fewest turns, and every affected game was replayed by every model or baseline that had evaluated it. The analysis uses the corrected records.
// src: cited git commits; docs/DECISIONS.md correction 27; analysis/manifest.toml

#pagebreak()
= Full component effects <app:components>

Each row reports both paired contrasts for one component. “Add” compares map plus the component with map alone. “Full” compares full context with full context minus that component. Positive values mean including the component helps. Intervals resample puzzles; Holm correction covers eight won-rate tests per model. Won-rate changes are proportions.
// src: analysis/out/components.md

#include "component_table.typ"

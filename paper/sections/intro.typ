#import "../lib.typ": todo

= Introduction

A non-generative decision model returns probabilities over supplied options. For sequential control, those selections must compose into a route, rather than merely look plausible individually. Jev's use in chess and software control motivates testing this distinction in an inspectable environment @saplin2026jev @mobilejev @jevultrafast. We study a fully observed symbolic world: the map already contains the information needed to navigate, while the controller varies its representation and the execution between observations.
// src: paper/references.bib; README.md; src/system_one_control/prompts.py; src/system_one_control/world.py

"System-One" refers to fast decisions without deliberate reasoning, after the System 1 / System 2 distinction; Laya calls its decision interface `system_one`.
// src: README.md; src/system_one_control/players/local.py

Four research questions guide the report:

+ *RQ1:* How well do non-generative models complete navigation from a complete symbolic state?
+ *RQ2:* How do local descriptions, interaction history, simulated action outcomes and explicit subgoals affect performance?
+ *RQ3:* How does performance vary across action formulations with different sequence lengths, option counts and observation intervals?
+ *RQ4:* How informative are returned probabilities, and what performance is obtained at the measured inference cost and latency?

We contribute a controlled environment with exact, tie-preserving move labels; a diagnostic evaluation of representations and action formulations; and empirical results with raw trajectories, replay validation and reproducible analysis. Solver verification is established in prior planning evaluation @valmeekam2022planbench; our focus is its diagnostic use for non-generative decision models.
// src: README.md; analysis/README.md; paper/references.bib

#import "../lib.typ": todo

= Introduction

A model may choose a sensible action when shown a single situation, yet struggle when its own decisions determine what happens next. We test this in a small gridworld where every optimal move can be computed exactly.

A non-generative decision model returns probabilities over supplied options. In sequential control, those choices must guide the agent all the way to the goal. Jev's use in chess and software control motivates this test @saplin2026jev @mobilejev @jevultrafast. The map contains all information needed to navigate. We vary the input descriptions and the actions available between observations.
// src: paper/references.bib; README.md; src/system_one_control/prompts.py; src/system_one_control/world.py

"System-One" refers to fast decisions without deliberate reasoning, after the System 1 / System 2 distinction. We evaluate Laya's Typed-Decisions checkpoint, called Laya below; its decision interface is `system_one`.
// src: src/system_one_control/players/local.py

Five research questions guide the report:

+ *RQ1:* How often do models complete games?
+ *RQ2:* Which added input descriptions help?
+ *RQ3:* Do good decisions on an exam of fixed positions, shared by all models, translate into completed games?
+ *RQ4:* What changes when actions contain sequences of steps?
+ *RQ5:* How informative are the returned probabilities, and at what cost and latency?

We provide exact labels that accept every equally optimal move, and tests of how input descriptions and available actions affect performance. Raw trajectories, replay validation and reproducible analysis accompany the results. Solver verification is established in prior planning evaluation @valmeekam2022planbench. Here it lets us inspect decisions by non-generative models.
// src: README.md; analysis/README.md; paper/references.bib

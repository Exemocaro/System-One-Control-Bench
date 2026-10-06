#import "../lib.typ": todo

= Discussion and limitations <sec:limitations>

*Single decisions versus whole games.* With full context, Jev answers 90% of the exam positions optimally, yet it wins only 57% of its games. Several things probably contribute. In its own games, a model reaches positions that a good player would never see, so its mistakes compound @ross2011. A long game gives many chances to fail: if each of ten moves were right 90% of the time, independently, all ten would be right only 35% of the time. Real games are less simple, because a mistake can be corrected, but the arithmetic shows how a high score per move can sit next to a modest success rate. Finally, as Greedy (walls) shows, most positions are easy, and games are decided by the few that need a detour. We did not measure how much each of these explanations contributes.
// src: analysis/out/exam.md; analysis/out/main.md

*What helps.* For Jev, full context almost removes blocked moves (0.4%), yet it still loses 43% of its games, so avoiding walls is only part of finding the way. Move outcomes give Jev its largest gain when added to map only (+16 points), though for DeepSeek V4.1 Flash the surroundings help more. Once the other components are present, removing any one of them rarely makes a clear difference; the only significant exception is move outcomes for Gemma 4 26B. We did not separate a component's content from the extra text it adds.
// src: analysis/out/main.md; analysis/out/components.md

*Limitations.*

- We test one small symbolic world, with five or ten puzzles per level and no held-out set. The prompts were written, using a few test games, before the puzzles were generated.
- Each result comes from one game per puzzle. Jev and DeepSeek V4.1 Flash give different answers to identical requests, and Gemma 4 26B and DeepSeek V4.1 Flash (reasoning) probably do too, so a rerun would play different games. The intervals cover the choice of puzzles, not this variation (@app:reproducibility).
- The move rules change several things together (options, text length, steps between looks at the board). Two smaller differences also come with them. The subgoal question asks for the "shortest path" under the fixed-length rules and for the way "that takes the fewest turns" under the up-to rules (a turn here is a move); both are scored by moves. And since the move limit counts moves, longer moves allow more steps: a four-step puzzle allows 8 steps under `compass` but 12 under `three-moves`.
- Levels differ in layout as well as route length, so the level results do not isolate distance.
- Providers, inference limits and hardware differ between models. Laya was used outside the tasks it was trained for. Costs are missing for Jev and the local models.
// src: analysis/out/coverage.md; src/system_one_control/world.py; src/system_one_control/prompts.py; paper/references.bib

#include "leaderboard.typ"

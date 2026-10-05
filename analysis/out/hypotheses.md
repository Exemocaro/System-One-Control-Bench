| Hypothesis | Observed | Criterion met |
| --- | --- | --- |
| H1: under map only, Jev beats random but not greedy (walls), on won rate and progress | success rate vs Random: +0.28 [+0.19, +0.37]; progress vs Random: +0.18 [+0.09, +0.26]; success rate vs Greedy (walls): -0.05 [-0.12, +0.02]; progress vs Greedy (walls): -0.05 [-0.11, +0.01]; Jev is not shown to beat Greedy (walls), nor shown not to | partly |
| H2: Jev's wins fall with the level; no condition wins half of the planning puzzles | success rate falls by 0.046 to 0.061 per level; planning puzzles are the 63 that Greedy (walls) loses, and the best condition on them wins 0.40 (full context minus surroundings) | yes |
| H3: simulated action outcomes help most (best map+X, worst everything-X, on progress) | progress, map + one component: move outcomes 0.61, move history 0.58, surroundings 0.57, subgoal 0.46; lowest full context minus one: full context minus move history 0.63 | partly |
| H4: explicit subgoal is second among additions, and helps mostly from level 3 up | ranks 4 of 4; progress gain +0.02 at levels 3 and up, +0.10 at levels 1-2 | no |
| H5: interaction history alone adds almost nothing (within 0.05 progress of map) | progress change +0.15 [+0.11, +0.21] | no |
| H6: full context has the best progress of the ten conditions and wins at least 28/100 | best progress: full context minus subgoal (0.73); full context wins 57/100 | partly |
| H7: Jev is overconfident, but its p(chosen) still ranks its moves | chosen move's mean probability 0.72, but 0.51 of chosen moves optimal; optimal at probability 0.9 or more: 0.74 (3895 moves), below 0.9: 0.42; yet a higher-probability bin is not always more often optimal | partly |

// src: analysis/out/hypotheses.md; generated verbatim from matching CSV
#figure(table(columns: (1fr, 1.5fr, auto), stroke: none, inset: 3pt,
table.header([Hypothesis], [Observed result], [Criterion met]),
text("H1: under map only, Jev beats random but not greedy (walls), on won rate and progress"), text("won vs random: +0.28 [+0.19, +0.37]; progress vs random: +0.18 [+0.09, +0.26]; won vs greedy-walls: -0.05 [-0.12, +0.02]; progress vs greedy-walls: -0.05 [-0.11, +0.01]"), text("yes"),
text("H2: Jev's wins fall with the level; no condition wins half of the planning puzzles"), text("won-vs-level slope -0.061 to -0.046 per level; best on the 63 planning puzzles: 0.40 (everything-surroundings); planning: the 63 puzzles greedy-walls loses (100 - 37)"), text("yes"),
text("H3: simulated action outcomes help most (best map+X, worst everything-X, on progress)"), text("map+X: lookahead 0.61, memory 0.58, surroundings 0.57, subgoal 0.46; everything-X lowest: memory 0.63"), text("partly"),
text("H4: explicit subgoal is second among additions, and helps mostly from level 3 up"), text("rank 4 of 4; progress gain +0.02 at levels 3+, +0.10 at 1-2"), text("no"),
text("H5: interaction history alone adds almost nothing (within 0.05 progress of map)"), text("progress change +0.15 [+0.11, +0.21]"), text("no"),
text("H6: full context has the best progress of the ten conditions and wins at least 28/100"), text("best progress: everything-subgoal (0.73); full context wins 57/100"), text("partly"),
text("H7: Jev is overconfident, but its p(chosen) still ranks its moves"), text("mean p(chosen) 0.72 vs optimal share 0.51; optimal at p >= 0.9: 0.74 (3895 moves), below: 0.42"), text("yes"),
), caption: [Hypotheses specified before the main evaluation. Statements, observations and verdicts come from the analysis table; H2 includes a definition of its planning subset.]) <tab:hyp>

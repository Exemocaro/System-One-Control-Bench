#import "../lib.typ": todo

= Benchmark design <sec:benchmark>

A puzzle contains walls (`#`), floor (`.`), a moving piece (`A`), goal (`G`), and optionally a key (`K`) and locked door (`D`). Compass steps move north, south, east or west. Collecting the key allows passage through the door; a wall or locked door otherwise blocks movement. Reaching the goal wins. Breadth-first search over position, inventory and door state labels every move that begins a shortest route, preserving ties.
// src: README.md; src/system_one_control/board.py; solver.py

#include "example_figure.typ"

The 100 puzzles span levels 1, 2, 3, 4, 5, 6, 8, 10, 12, 15 and 20, where level is shortest distance in compass steps. Levels 1 and 2 contain five puzzles each; others ten. Seeded generation creates rooms and mazes, with one hand-made level-10 maze. Higher levels add mandatory detours and key-door dependencies; the wall-aware greedy baseline fails on all 40 puzzles at levels 10 and above. Extra outer-wall rings in half of the puzzles at levels 12, 15 and 20 add irrelevant map text without changing the interior.
// src: README.md; docs/DECISIONS.md; analysis/out/levels.md

A *move* is one model decision; a *step* is a compass displacement within it. Action spaces offer one step (4 options), exactly two (16), up to two (20), exactly three (64), or up to three (84). All sequences are offered. A blocked step is wasted and execution continues; reaching the goal immediately ends the move. The next observation follows execution. Changing the formulation changes how many moves are offered, how much text describes them, and how many steps execute before the next observation. Several sequences can also end at the same position. These experiments compare the whole interface rather than option count alone.
// src: rules.py; game.py; README.md

Every request includes rules, the numbered map, position, inventory and object coordinates. A *local state description* explains adjacent cells and relative object locations. *Interaction history* lists prior moves and their results. *Simulated action outcomes* tell the model what would happen after each option. An *explicit subgoal* names the next target. The local descriptions and simulations are computed from information already present in the map. History is not needed to reconstruct the state, but may expose loops. The ten conditions add each component to the map alone or remove it from full context (@tab:conditions).
// src: conditions.py; examples/; review interpretation framed as possibility

#figure(table(columns: (auto, 1fr), align: left, stroke: none, inset: 2pt,
  table.header([Artifact ID], [Paper name]),
  text(font: "DejaVu Sans Mono", size: 9pt)[map], [Map alone],
  text(font: "DejaVu Sans Mono", size: 9pt)[map+surroundings], [Map with local state description],
  text(font: "DejaVu Sans Mono", size: 9pt)[map+memory], [Map with interaction history],
  text(font: "DejaVu Sans Mono", size: 9pt)[map+lookahead], [Map with simulated action outcomes],
  text(font: "DejaVu Sans Mono", size: 9pt)[map+subgoal], [Map with explicit subgoal],
  text(font: "DejaVu Sans Mono", size: 9pt)[everything], [Full context],
  text(font: "DejaVu Sans Mono", size: 9pt)[everything-surroundings], [Full context without local state description],
  text(font: "DejaVu Sans Mono", size: 9pt)[everything-memory], [Full context without interaction history],
  text(font: "DejaVu Sans Mono", size: 9pt)[everything-lookahead], [Full context without simulated action outcomes],
  text(font: "DejaVu Sans Mono", size: 9pt)[everything-subgoal], [Full context without explicit subgoal]),
  placement: top, caption: [Condition-ID mapping. Full context includes all four components.]) <tab:conditions>
// src: examples/; README.md

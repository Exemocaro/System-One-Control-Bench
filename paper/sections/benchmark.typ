#import "../lib.typ": todo

= Benchmark design <sec:benchmark>

== Puzzles

Each puzzle is a small grid map (@fig:example). A piece, `A`, must reach the goal, `G`, and walls, `#`, are in the way. Some puzzles also have a key, `K`, and a locked door, `D`: the piece picks up the key by stepping onto it, and the door opens only when the piece walks into it carrying the key. A *step* moves the piece one cell north, south, east or west. A step into a wall, or into the door without the key, is *blocked*, and the piece stays where it is.
// src: README.md; src/system_one_control/world.py

An exact solver (a breadth-first search over the piece's position, the key and the door) knows how many steps each position is from the goal. We call a move *optimal* if it starts a shortest route to the goal. When several moves are equally good, all of them count as optimal.
// src: src/system_one_control/world.py

The 100 puzzles are grouped into levels 1, 2, 3, 4, 5, 6, 8, 10, 12, 15 and 20, where the level is the length of the shortest route in steps. Levels 1 and 2 have five puzzles each, and the others ten. A seeded generator made rooms and mazes; one level-10 maze is hand-made. Keys appear from level 3, and every puzzle from level 10 up has one. Higher levels also need detours away from the goal. Half of the puzzles at levels 12, 15 and 20 have extra rings of outer wall, which make the map text longer without changing the puzzle.
// src: README.md; src/system_one_control/puzzles.py; analysis/out/levels.md

#include "example_figure.typ"

== Move rules

A *move* is one decision by the model. Under the basic `compass` rules, a move is a single step. Under the other four, the *sequence rules*, a move can be a sequence of two or three steps (@tab:rules), and every possible sequence is offered. Two of them fix the number of steps (`two-moves`, `three-moves`); the two *up-to* rules also allow shorter moves. The steps run one after another: a blocked step is wasted and the rest still run, and reaching the goal ends the move at once. The model sees the new position only after the whole move.

#figure(table(columns: (auto, auto, auto), align: (left, left, right), stroke: none, inset: 2.5pt,
  table.header([Rules], [One move is], [Options]),
  [`compass`], [one step], [4],
  [`two-moves`], [exactly two steps], [16],
  [`up-to-two-moves`], [one or two steps], [20],
  [`three-moves`], [exactly three steps], [64],
  [`up-to-three-moves`], [one, two or three steps], [84]),
  placement: auto, caption: [The five move rules. Every sequence of steps is offered, including ones that walk into walls.]) <tab:rules>
// src: src/system_one_control/world.py

Longer moves change several things at once: the number of options, the length of each option's text, and how many steps happen before the model sees the board again. Several sequences can also end in the same place. We compare the rules as a whole and do not separate these effects.

A game is won when the piece reaches the goal. It is lost when the model has used twice as many moves as the solver needs under the same rules.
// src: src/system_one_control/world.py; src/system_one_control/bench.py; README.md

== What the model is told

Every request contains the rules of the game, the map with numbered rows and columns, the piece's position, whether it carries the key, and where the key, door and goal are. We call this basic request *map only*. Four *components* can be added to it:

- *Surroundings:* what is next to the piece in each direction, and how far away each object is ("The key is 1 south of you").
- *Move history:* every move so far and what it did.
- *Move outcomes:* each option also says what it would do ("move south (down): you move to (7, 2) and pick up the key").
- *Subgoal:* instead of "What is the best next move?", the question names the next target: the key, then the door, then the goal.

Surroundings, move outcomes and the subgoal are worked out from the map, so they add no new information; they only make it easier to use. The move history is not needed to know where the piece is, but it can show that the piece is going in circles.

There are ten *conditions* (@tab:conditions): map only, the map plus one component, all four components (*full context*), and full context minus one component. Most results compare map only with full context. @app:prompts shows two complete requests.
// src: src/system_one_control/prompts.py; examples/everything.json

#figure(table(columns: (auto, auto), align: left, stroke: none, inset: 2.5pt,
  table.header([Condition name in the code], [Name in this report]),
  [`map`], [map only],
  [`map+surroundings`], [map + surroundings],
  [`map+memory`], [map + move history],
  [`map+lookahead`], [map + move outcomes],
  [`map+subgoal`], [map + subgoal],
  [`everything`], [full context],
  [`everything-surroundings`], [full context minus surroundings],
  [`everything-memory`], [full context minus move history],
  [`everything-lookahead`], [full context minus move outcomes],
  [`everything-subgoal`], [full context minus subgoal]),
  placement: none, caption: [The ten conditions. Full context has all four components.]) <tab:conditions>
// src: examples/everything.json; README.md

== The exam

In a game, a model's own choices decide which positions it sees next, so after the first move two models may no longer answer the same questions. The exam removes this difference. It has 495 fixed positions, five from each puzzle (four at level 1), that every player answers. Every model answers each position once with map only and once with full context (the baselines, which do not read the request, answer once), under compass rules, and we check whether the answer is optimal. The exam score is the share of optimal answers, with each puzzle counting equally. Each position is reached by playing a fixed list of moves from the start through the normal game, so a full-context request also lists those moves in its history.

There are five kinds of position: the *start*; *on-route*, partway along a shortest route; *off-route*, one wrong move away from a shortest route; *after-blocked*, just after a move into a wall; and *late*, in the second half of the route and after the key where there is one. Each puzzle gets one position of each kind where its layout allows; the remaining places are filled with extra off-route or after-blocked positions (@app:reproducibility gives the counts). A mistake on the exam costs nothing later, so the exam measures single decisions, not whole games.
// src: scripts/make_exam.py; src/system_one_control/exam_items.py; src/system_one_control/exam.py

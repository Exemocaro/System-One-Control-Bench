#import "../lib.typ": todo

= Two example requests <app:prompts>

Both requests below are for the position in @fig:example, shown in full; lines wrap only to fit the page. Every model gets the same three parts: the state, the question and the options. Jev receives them as the fields of its API. Chat models receive them in one message, after this instruction: "You are playing a puzzle on a grid. You are given the state of the game, a question and a list of options, each with an id such as option_3. Reply with the id of the one option you choose." The repository's `examples/` directory holds the request for every input condition and move rule.
// src: examples/map.json; examples/up-to-two-moves/everything.json; src/system_one_control/players/remote.py

== Compass rules, map only

#include "example_map.typ"

== Up-to-two-moves rules, full context

With full context the state adds the surroundings and the move history, each option says what it would do, and the question names the next target.

#include "example_sequence.typ"

#pagebreak()
= Hypotheses written before the main runs <app:hypotheses>

#include "hypothesis_table.typ"

#pagebreak()
= Setup and reproducibility <app:reproducibility>

#include "reproducibility.typ"

#pagebreak()
= All component effects <app:components>

#include "component_table.typ"

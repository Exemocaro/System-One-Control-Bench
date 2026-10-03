// src: examples/everything.json; frozen illustrative route, data from paper/tables.py
#figure(block(breakable: false, grid(columns: (auto, 1fr), gutter: 12pt,
raw(@MAP@, block: true),
[*Map alone:* position (7, 1), empty inventory, map and object coordinates; "What is the best next move?"\
*Simulated outcomes:* "move south (down): you move to (7, 2) and pick up the key".\
Shortest route: south, west, west, south, west, west, west, west, south.])),
kind: image, supplement: [Figure], caption: [The frozen example position. Stars trace one shortest route through K and D to G; X marks east, a suboptimal move toward open floor. Stars and X replace floor only in this figure. Appendix A gives its full-context request.]) <fig:example>

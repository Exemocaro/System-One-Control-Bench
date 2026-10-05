// src: examples/everything.json; frozen illustrative route, data from paper/tables.py
#figure(block(breakable: false, grid(columns: (auto, 1fr), gutter: 12pt,
block[#show raw: set text(size: 11pt)
#raw(@MAP@, block: true)],
align(left)[*Map only:* the map, the position (7, 1), "You are carrying nothing", where the objects are, and "What is the best next move?"\
*With move outcomes:* each option says what it does, such as "move south (down): you move to (7, 2) and pick up the key".\
*Shortest route:* south, west, west, south, west, west, west, west, south (nine steps).])),
kind: image, supplement: [Figure], caption: [An example position. Stars trace a shortest route through K and D to G; X marks where moving east leads, which is not optimal. Stars and X appear only in this figure. @app:prompts shows two complete requests for this position.]) <fig:example>

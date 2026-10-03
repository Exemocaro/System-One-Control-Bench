#import "lib.typ": todo

#set document(title: "Evaluating Non-Generative Decision Models in Sequential Gridworld Tasks", author: "Mateus Pereira")
#set page(paper: "a4", margin: 2.2cm, numbering: "1")
#set text(font: "New Computer Modern", size: 11pt, lang: "en")
#set par(justify: true, leading: 0.5em, spacing: 0.8em)
#set heading(numbering: "1.1", supplement: [Section])
#show heading: set block(above: 1.4em, below: 0.8em)
#show heading.where(level: 1): set text(size: 13pt)
#show heading.where(level: 2): set text(size: 11.5pt)
#show raw: set text(font: "DejaVu Sans Mono", size: 0.8em)
#show link: underline
#set figure(gap: 0.8em)
#show figure.caption: set text(size: 9pt)
#show figure.caption: it => context [*#it.supplement #it.counter.display(it.numbering)#it.separator*#it.body]
#show figure.where(kind: table): set figure.caption(position: top)
#show figure.where(kind: table): set text(size: 9pt)
#show figure.where(kind: table): set par(justify: false)
#show figure.where(kind: table): set block(breakable: true)
#set list(indent: 0.6em, spacing: 0.6em)

#align(center)[
  #set par(justify: false)
  #text(size: 17pt, weight: "bold", hyphenate: false)[Evaluating Non-Generative Decision Models in Sequential Gridworld Tasks]
  #v(0.8em)
  Mateus Pereira \
  Independent researcher
]
#v(1em)

#align(center)[*Abstract*]
#block(inset: (x: 1.2cm))[#include "sections/abstract.typ"]

#include "sections/intro.typ"
#include "sections/related.typ"
#include "sections/benchmark.typ"
#include "sections/players.typ"
#include "sections/results.typ"
#include "sections/discussion.typ"
#include "sections/conclusion.typ"

#context metadata(here().page()) <report:main-end>
#pagebreak()
#bibliography("references.bib", title: "References", style: "ieee")

#pagebreak()
#counter(heading).update(0)
#set heading(numbering: "A.1", supplement: [Appendix])
#context metadata(here().page()) <report:appendix-start>
#include "sections/appendix.typ"
#context metadata(here().page()) <report:end>

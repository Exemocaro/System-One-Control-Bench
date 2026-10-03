// src: analysis/out/components.md; all models and contrasts from matching CSV
#figure([
#set text(size: 8.5pt)
#set par(leading: 0.25em)
#table(columns: (1.2fr, 1fr, 1fr, 0.55fr, 1fr, 1fr, 0.55fr), stroke: none, inset: 2pt,
table.header([Component], [Add: won change], [Add: progress], [Add: Holm p], [Full: won change], [Full: progress], [Full: Holm p]),
@ROWS@
)], caption: [Complete paired component effects. Brackets give 95% intervals. Add and Full both report the effect of including the component.]) <tab:components>

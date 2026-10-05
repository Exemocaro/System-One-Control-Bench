// src: analysis/out/components.md; all models and contrasts from matching CSV
#figure([
#set text(size: 8.5pt)
#set par(leading: 0.25em)
#table(columns: (1.05fr, 0.85fr, 1.3fr, 0.45fr, 0.85fr, 1.3fr, 0.45fr), stroke: none, inset: 2pt, align: (x, y) => if x == 0 { left } else { center },
table.header(table.cell(rowspan: 2, align: bottom)[Component], table.cell(colspan: 3)[Added to map only], table.cell(colspan: 3)[Full context vs. full context without it], [Success (points)], [Progress], [p], [Success (points)], [Progress], [p]),
@ROWS@
)], caption: [Effect of including each component, for every model (compass rules, 100 paired puzzles). _Added to map only_ compares map + component with map only; the second group compares full context with full context minus the component. Positive values mean the component helps. Success-rate changes are in percentage points, progress changes on the 0--1 scale; brackets give 95% intervals. p is McNemar's exact test on games won, Holm-corrected over each model's eight tests.]) <tab:components>

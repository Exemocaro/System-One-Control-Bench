# Short report

Build from the repository root:

```powershell
uv run python paper/tables.py
typst compile --root . paper/main.typ
```

Edit prose directly in `sections/*.typ`, preserving the `// src:` comments. No script generates prose. `tables.py` reads the current `analysis/out/*.csv` tables and frozen `examples/everything.json`, and writes only the included main, hypothesis and component tables and example request/figure data. Editable layout and captions are in `templates/*.typ`; the example overlay follows the previously checked route in the frozen position.

Check the script with `uv run ruff check paper` and `uv run ruff format --check paper` (line length 100).

The seven figures are the example, main results, component effects, action formulations, the fixed-state exam, completion by level and reliability. All source plots remain unchanged.

The appendix contains one complete example request, all seven hypotheses with verbatim analysis verdicts, prompt history and all component contrasts for every model. The body keeps two visible TODOs: author and repository URL. Other follow-up work is recorded in `.team/paper-todo.md`. Page-boundary metadata in `main.typ` records the main-text end, appendix start and total page count.

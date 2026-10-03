# Short report

Build from the repository root:

```powershell
python paper/build_appendices.py
typst compile --root . paper/main.typ
```

`build_appendices.py` generates the compact main results table, result prose, abstract, conclusion, hypothesis table, full component-effects table and example figure/request. It reads the current `analysis/out/*.csv` tables and the complete frozen `examples/everything.json`, and checks the example route with BFS. `make_appx_tables.py` calls the same generators for compatibility.

The six figures are the example, main results, component effects, action formulations, completion by level and reliability. All source plots remain unchanged.

The appendix contains one complete example request, all seven hypotheses with verbatim analysis verdicts, prompt history and all component contrasts for every model. The body keeps three visible TODOs: author, repository URL and fixed-state results. Other follow-up work is recorded in `.team/paper-todo.md`. Page-boundary metadata in `main.typ` records the main-text end, appendix start and total page count.

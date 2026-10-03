# Build the paper

Install uv and Typst 0.15 or newer, then run from the repository root:

```powershell
uv sync
uv run --with matplotlib python analysis/analyze.py
uv run python paper/tables.py
typst compile --root . paper/main.typ paper/main.pdf
```

The analysis command rebuilds tables and plots from saved results without API calls. `paper/tables.py` refreshes generated tables and example data; prose is in `sections/*.typ` and table layouts/captions are in `templates/*.typ`.

Check the generator with `uv run ruff check paper` and `uv run ruff format --check paper`. Preview `paper/main.typ` in VS Code with Tinymist, or run `typst watch --root . paper/main.typ paper/main.pdf`.

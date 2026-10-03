"""Generate included tables and example data; edit prose directly in sections/*.typ."""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAPER = ROOT / "paper"


def read(name):
    with (ROOT / "analysis/out" / f"{name}.csv").open(encoding="utf-8") as source:
        return list(csv.DictReader(source))


def write(name, content):
    (PAPER / "sections" / f"{name}.typ").write_text(content, encoding="utf-8", newline="\n")


def table(name, rows):
    template = (PAPER / "templates" / f"{name}.typ").read_text(encoding="utf-8")
    write(name, template.replace("@ROWS@", "\n".join(rows)))


def cells(values):
    return ", ".join(f"text({json.dumps(value, ensure_ascii=False)})" for value in values) + ","


def interval(row, field, scale=1):
    values = [float(row[field + suffix]) * scale for suffix in ("", " low", " high")]
    mean, low, high = [f"{value:.{0 if scale == 100 else 2}f}" for value in values]
    return f"{mean}{'%' if scale == 100 else ''} [{low}, {high}]"


def main_table():
    records = read("main")
    rows = {(row["Model"], row["Input"]): row for row in records}
    output = []
    for model in dict.fromkeys(row["Model"] for row in records):
        won, efficiency = [], []
        for condition in ("map only", "full context"):
            row = rows.get((model, condition))
            won.append(interval(row, "Won rate", 100) if row else "—")
            efficiency.append(
                f"{float(row['Progress']):.3f} / {float(row['SPL']):.3f}" if row else "—"
            )
        output.append(cells([model, *won, *efficiency]))
    table("main_table", output)


def components():
    records = read("components")
    rows = {(row["Model"], row["Component"], row["Direction"]): row for row in records}
    output = []
    for model in dict.fromkeys(row["Model"] for row in records):
        output.append(f'table.cell(colspan: 7, text(weight: "bold", {json.dumps(model)})),')
        for name in dict.fromkeys(row["Component"] for row in records):
            values = [name]
            for direction in ("added to map only", "removed from full context"):
                row = rows[(model, name, direction)]
                values += [interval(row, field) for field in ("Won rate change", "Progress change")]
                values.append(f"{float(row['Holm p']):.3f}")
            output.append(cells(values))
    table("component_table", output)


def example():
    request = json.loads((ROOT / "examples/everything.json").read_text(encoding="utf-8"))
    question = request["questions"]["move"]
    lines = ["state:", request["state"], "", "model: " + request["model"]]
    lines += [f"questions.move.{key}: {question[key]}" for key in ("type", "instructions")]
    lines += ["questions.move.criteria:", *[f"  {k}: {v}" for k, v in question["criteria"].items()]]
    content = "\n".join(lines)
    write(
        "example_request",
        "// src: examples/everything.json; complete fields, no added display line breaks\n"
        "#show raw: set text(size: 7.5pt)\n#set par(leading: 0.2em)\n"
        f'#raw({json.dumps(content)}, block: true, lang: "text")\n',
    )
    board = [
        list(line.split()[1])
        for line in request["state"].splitlines()
        if len(line.split()) == 2 and line.split()[0].isdigit()
    ]
    for x, y in ((6, 2), (5, 2), (5, 3), (4, 3), (3, 3), (2, 3)):
        assert board[y][x] == ".", "Frozen example changed; review the illustrative route."
        board[y][x] = "*"
    board[1][8] = "X"
    drawn = "   0123456789\n" + "\n".join(f"{y:2} {''.join(row)}" for y, row in enumerate(board))
    template = (PAPER / "templates/example_figure.typ").read_text(encoding="utf-8")
    write("example_figure", template.replace("@MAP@", json.dumps(drawn)))


if __name__ == "__main__":
    main_table()
    table("hypothesis_table", [cells(row.values()) for row in read("hypotheses")])
    components()
    example()

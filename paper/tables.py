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


def two_places(row, field):
    """The value and its interval as the analysis's tables print them, to two decimals."""
    return [float(f"{float(row[field + suffix]):.2f}") for suffix in ("", " low", " high")]


def interval(row, field, scale=1):
    values = [value * scale for value in two_places(row, field)]
    mean, low, high = [f"{value:.{0 if scale == 100 else 2}f}" for value in values]
    return f"{mean}{'%' if scale == 100 else ''} [{low}, {high}]"


def main_table():
    records = read("main")
    rows = {(row["Model"], row["Condition"]): row for row in records}
    output = []
    for model in dict.fromkeys(row["Model"] for row in records):
        won, efficiency = [], []
        for condition in ("map only", "full context"):
            row = rows.get((model, condition))
            won.append(interval(row, "Success rate", 100) if row else "—")
            efficiency.append(
                f"{float(row['Progress']):.3f} / {float(row['SPL']):.3f}" if row else "—"
            )
        output.append(cells([model, *won, *efficiency]))
    table("main_table", output)


def signed(row, field, points=False):
    """A change and its interval: +13 [7, 20] in percentage points, or +0.14 [0.09, 0.20]."""
    shown = [f"{v * 100:.0f}" if points else f"{v:.2f}" for v in two_places(row, field)]
    mean, low, high = [v.removeprefix("-") if float(v) == 0 else v for v in shown]
    text = f"{'' if mean.startswith('-') or float(mean) == 0 else '+'}{mean} [{low}, {high}]"
    return text.replace("-", "\N{MINUS SIGN}")


def exam_table():
    games = {(row["Model"], row["Condition"]): row for row in read("main")}
    output = []
    for row in read("exam"):
        game = games[(row["Model"], row["Condition"])]
        output.append(
            cells(
                [
                    row["Model"],
                    row["Condition"],
                    interval(row, "Exam optimal rate", 100),
                    f"{float(row['Own games optimal rate']) * 100:.0f}%",
                    f"{float(game['Success rate']) * 100:.0f}%",
                ]
            )
        )
    table("exam_table", output)


def components():
    records = read("components")
    rows = {(row["Model"], row["Component"], row["Direction"]): row for row in records}
    output = []
    for model in dict.fromkeys(row["Model"] for row in records):
        output.append(f'table.cell(colspan: 7, text(weight: "bold", {json.dumps(model)})),')
        for name in dict.fromkeys(row["Component"] for row in records):
            values = [name]
            for direction in ("added to map only", "full context vs. full context minus it"):
                row = rows[(model, name, direction)]
                values += [signed(row, "Success rate change", True), signed(row, "Progress change")]
                p_value = float(row["Holm p"])
                values.append("<0.001" if p_value < 0.001 else f"{p_value:.3f}")
            output.append(cells(values))
    table("component_table", output)


def rules_table():
    records = read("action_spaces")
    rows = {(r["Model"], r["Move rules (options)"], r["Condition"]): r for r in records}
    rules = list(dict.fromkeys(r["Move rules (options)"] for r in records))
    output = []
    for model in dict.fromkeys(r["Model"] for r in records):
        if not all((model, rule, "full context") in rows for rule in rules):
            continue  # baselines, and models that played compass only
        for condition in ("map only", "full context"):
            won = [float(rows[(model, rule, condition)]["Success rate"]) for rule in rules]
            output.append(cells([model, condition, *[f"{w * 100:.0f}%" for w in won]]))
    table("rules_table", output)


def request_text(path):
    """A frozen request as every model gets it: the state, the question and the options."""
    request = json.loads((ROOT / "examples" / path).read_text(encoding="utf-8"))
    question = request["questions"]["move"]
    options = [f"{k}: {v}" for k, v in question["criteria"].items()]
    lines = ["STATE", request["state"], "", "QUESTION", question["instructions"], "", "OPTIONS"]
    return request, "\n".join([*lines, *options])


def example():
    for name, path in [
        ("example_map", "map.json"),
        ("example_sequence", "up-to-two-moves/everything.json"),
    ]:
        write(
            name,
            f"// src: examples/{path}; complete fields, no added display line breaks\n"
            "#show raw: set text(size: 7.5pt)\n#set par(leading: 0.55em)\n"
            f'#raw({json.dumps(request_text(path)[1])}, block: true, lang: "text")\n',
        )
    request, _ = request_text("everything.json")
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
    exam_table()
    table("hypothesis_table", [cells(row.values()) for row in read("hypotheses")])
    components()
    rules_table()
    example()

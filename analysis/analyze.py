"""Every table and figure in the paper, from the results files named in manifest.toml.

Run from the repository root: uv run --with matplotlib python analysis/analyze.py
Read analysis/README.md before changing anything here.
"""

from __future__ import annotations

import csv
import json
import statistics
import textwrap
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import metrics
from matplotlib.legend_handler import HandlerTuple
from matplotlib.patches import Patch

from system_one_control.bench import load
from system_one_control.puzzles import load_puzzles
from system_one_control.world import Solver, make_rules

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "analysis" / "out"

# Ordered by the number of options each offers.
RULES = {
    "compass": 4,
    "two-moves": 16,
    "up-to-two-moves": 20,
    "three-moves": 64,
    "up-to-three-moves": 84,
}
BASELINES = {
    "solver": ("Solver", "black"),
    "greedy-walls": ("Greedy (walls)", "#7F7F7F"),
    "greedy": ("Greedy", "#A6A6A6"),
    "random": ("Random", "#CCCCCC"),
}
MODELS = {
    "jev": ("Jev", "#D62728"),
    "laya": ("Laya", "#7FC8F8"),
    "gliclass": ("GLiClass", "#F2D600"),
    "gemma-4-26b": ("Gemma 4 26B", "#4CD137"),
    "qwen3.5-4b": ("Qwen3.5-4B", "#FF6A00"),
    "deepseek-v4.1-flash": ("DeepSeek V4.1 Flash", "#4D6BFE"),
    "deepseek-v4.1-flash-think": ("DeepSeek V4.1 Flash (reasoning)", "#0B1F7A"),
}
PLAYERS = BASELINES | MODELS
COMPONENTS = {
    "surroundings": "surroundings",
    "memory": "move history",
    "lookahead": "move outcomes",
    "subgoal": "subgoal",
}
INPUTS = {"map": "map only", "everything": "full context"}


def condition_name(condition: str) -> str:
    """The paper's name for a condition, such as "full context minus subgoal"."""
    for sign, word in [("+", " + "), ("-", " minus ")]:
        base, found, component = condition.partition(sign)
        if found:
            return {"map": "map", "everything": "full context"}[base] + word + COMPONENTS[component]
    return INPUTS[condition]


KINDS = ["start", "on-route", "off-route", "after-blocked", "late"]  # exam items


@dataclass(frozen=True)
class Game:
    player: str
    rules: str
    condition: str
    puzzle: str
    level: int
    won: bool
    progress: float  # at the closest point the game ever reached
    final_progress: float  # at the position the game ended on
    spl: float
    blocked: int  # moves that left the board unchanged
    error: bool  # the game ended on a player error
    moves: tuple  # the results file's move records


def load_games() -> list[Game]:
    puzzles = load_puzzles(ROOT / "puzzles")
    distances: dict[str, dict] = {}
    games: dict[tuple, Game] = {}
    for entry in tomllib.loads((ROOT / "analysis" / "manifest.toml").read_text("utf-8"))["results"]:
        for record in load(ROOT / "benchmarks" / entry["file"]):
            if record.player not in entry["players"]:
                continue
            assert record.rules == entry["rules"], f"{entry['file']} holds {record.rules} games"
            key = (record.player, record.rules, record.condition, record.puzzle)
            assert key not in games, f"two games for {key}"
            puzzle = puzzles[record.puzzle]
            rules = make_rules(record.rules)
            board, blocked = puzzle.board, 0
            for move in record.moves:
                found = rules.find_move(board, move.move) if move.move else None
                after = rules.apply(board, found) if found else board
                blocked += found is not None and after == board  # an error is not a move
                board = after
            if record.puzzle not in distances:  # in single steps, as levels are counted
                distances[record.puzzle] = Solver(rules.step_rules()).distances(puzzle.board)
            level = record.level
            games[key] = Game(
                record.player,
                record.rules,
                record.condition,
                record.puzzle,
                level,
                record.won,
                metrics.progress(level, record.closest),
                1.0 if record.won else metrics.progress(level, distances[record.puzzle].get(board)),
                metrics.spl(record.won, rules.moves_for(level), len(record.moves)),
                blocked,
                record.error is not None,
                record.moves,
            )
    return list(games.values())


def estimate(values: list[float]) -> tuple[float, float, float]:
    return (statistics.mean(values), *metrics.bootstrap_interval(values))


def paired(a: dict[str, Game], b: dict[str, Game], field: str) -> tuple[list, list]:
    shared = sorted(a.keys() & b.keys())
    return [getattr(a[p], field) for p in shared], [getattr(b[p], field) for p in shared]


def change(a: dict[str, Game], b: dict[str, Game], field: str) -> tuple[float, float, float]:
    """Mean of a - b over the puzzles both played, with a puzzle-level interval."""
    x, y = paired(a, b, field)
    return estimate([float(i) - float(j) for i, j in zip(x, y, strict=True)])


def write_table(name: str, header: list[str], rows: list[list]) -> None:
    """A Markdown and a CSV copy; an (estimate, low, high) cell becomes three CSV columns."""

    def text(cell):
        if isinstance(cell, tuple):
            return f"{cell[0]:.2f} [{cell[1]:.2f}, {cell[2]:.2f}]"
        return f"{cell:.3f}" if isinstance(cell, float) else str(cell)

    lines = ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
    lines += ["| " + " | ".join(text(cell) for cell in row) + " |" for row in rows]
    (OUT / f"{name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    columns = [
        c
        for h, cell in zip(header, rows[0], strict=True)
        for c in ([h, f"{h} low", f"{h} high"] if isinstance(cell, tuple) else [h])
    ]
    with (OUT / f"{name}.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(
            [v for cell in row for v in (cell if isinstance(cell, tuple) else (cell,))]
            for row in rows
        )


def tables(games: dict) -> None:
    rows = []
    for player, (name, _) in PLAYERS.items():
        for condition in ["map"] if player in BASELINES else INPUTS:
            g = list(games.get((player, "compass", condition), {}).values())
            if g:
                moves = sum(len(x.moves) for x in g)
                rows.append([name, INPUTS[condition], len(g), estimate([x.won for x in g])])
                rows[-1] += [estimate([x.progress for x in g])]
                rows[-1] += [statistics.mean(x.final_progress for x in g)]
                rows[-1] += [statistics.mean(x.spl for x in g), sum(x.blocked for x in g) / moves]
    header = ["Model", "Condition", "Games", "Success rate", "Progress"]
    header += ["Final-state progress", "SPL"]
    write_table("main", [*header, "Blocked moves"], rows)

    rows = []
    for player, (name, _) in MODELS.items():
        found = []
        for component, label in COMPONENTS.items():
            for direction, a, b in [
                ("added to map only", f"map+{component}", "map"),
                ("full context vs. full context minus it", "everything", f"everything-{component}"),
            ]:
                a, b = games[(player, "compass", a)], games[(player, "compass", b)]
                found.append([name, label, direction, change(a, b, "won")])
                found[-1] += [change(a, b, "progress"), metrics.mcnemar_p(*paired(a, b, "won"))]
        for row, adjusted in zip(found, metrics.holm([row[-1] for row in found]), strict=True):
            rows.append([*row, adjusted])
    header = ["Model", "Component", "Direction", "Success rate change", "Progress change"]
    write_table("components", [*header, "McNemar p", "Holm p"], rows)

    rows = []
    for player, (name, _) in PLAYERS.items():
        for rules, options in RULES.items():
            for condition in INPUTS:
                g = list(games.get((player, rules, condition), {}).values())
                if g:
                    rows.append([name, f"{rules} ({options})", INPUTS[condition], len(g)])
                    rows[-1] += [estimate([x.won for x in g]), estimate([x.progress for x in g])]
    header = ["Model", "Move rules (options)", "Condition", "Games", "Success rate", "Progress"]
    write_table("action_spaces", header, rows)

    rows = []
    for player, (name, _) in PLAYERS.items():
        for condition in ["map"] if player in BASELINES else INPUTS:
            g = list(games.get((player, "compass", condition), {}).values())
            for level in sorted({x.level for x in g}):
                won = [x.won for x in g if x.level == level]
                rows.append([name, INPUTS[condition], level, len(won), estimate(won)])
    write_table("levels", ["Model", "Condition", "Level", "Games", "Success rate"], rows)

    rows = []
    for player, (name, _) in MODELS.items():
        confidence, optimal, ties, gap = calibration_moves(games, player)
        if confidence:
            rows.append([name, len(confidence), statistics.mean(confidence)])
            rows[-1] += [statistics.mean(optimal)]
            rows[-1] += [metrics.expected_calibration_error(confidence, optimal)]
            rows[-1] += [metrics.brier_score(confidence, optimal)]
            rows[-1] += [statistics.mean(optimal) * (1 - statistics.mean(optimal)), ties, gap]
    header = ["Model", "Moves", "Mean p(chosen)", "Optimal share", "ECE", "Brier"]
    header += ["Brier of a constant", "Tied share"]
    write_table("calibration", [*header, "Max confidence - rescaled p_max"], rows)

    rows = []
    for player, (name, _) in MODELS.items():
        g = [
            x
            for (p, r, _), v in games.items()
            if p == player and r == "compass"
            for x in v.values()
        ]
        moves = [m for x in g for m in x.moves]
        costs = [m.cost for m in moves if m.cost is not None]
        tokens = [m.input_tokens for m in moves if m.input_tokens]
        rows.append([name, len(g), len(moves)])
        rows[-1] += [statistics.median(m.seconds for m in moves if m.seconds is not None)]
        rows[-1] += [statistics.mean(tokens) if tokens else ""]
        rows[-1] += [100 * sum(costs) / len(g) if costs else ""]
    header = ["Model", "Games", "Moves", "Median seconds per move", "Mean input tokens"]
    write_table("cost", [*header, "Cost per 100 games ($)"], rows)

    rows = []
    for (player, rules, condition), v in sorted(games.items()):
        rows.append([PLAYERS[player][0], rules, condition, len(v)])
        rows[-1] += [sum(x.error for x in v.values())]
    header = ["Model", "Rules", "Condition", "Games", "Games ended by an error"]
    write_table("coverage", header, rows)
    write_table("hypotheses", ["Hypothesis", "Observed", "Criterion met"], hypotheses(games))


def load_exam() -> dict[tuple, dict[str, list]]:
    """(player, condition) -> {puzzle: [(kind, optimal, p(chosen) or None) per answer]}.
    An answer that ended in an error counts as not optimal."""
    exam: dict = defaultdict(lambda: defaultdict(list))
    files = tomllib.loads((ROOT / "analysis" / "manifest.toml").read_text("utf-8"))["exam"]
    for player, file in files.items():
        for line in (ROOT / "exam" / file).read_text("utf-8").splitlines():
            record = json.loads(line)
            assert record["player"] == player, f"{file} holds {record['player']}"
            answer, failed = record["answer"], record["error"] is not None
            p = None if failed else (answer["probabilities"] or {}).get(answer["move"])
            puzzle, kind = record["item"]["puzzle"], record["item"]["kind"]
            exam[(player, record["condition"])][puzzle].append(
                (kind, not failed and answer["optimal"], p)
            )
    items = len((ROOT / "exam" / "items.jsonl").read_text("utf-8").splitlines())
    for key, by_puzzle in exam.items():
        assert sum(map(len, by_puzzle.values())) == items, f"{key} does not answer every item once"
    return exam


def exam_rate(by_puzzle: dict[str, list]) -> tuple[float, float, float]:
    """Optimal answers, averaged within each puzzle, then over puzzles (resampled)."""
    return estimate([statistics.mean(a[1] for a in v) for v in by_puzzle.values()])


def in_game_optimal(games: dict, player: str, condition: str, pooled: bool = False) -> float:
    """Optimal share of the moves in the player's own compass games: averaged within each game,
    then over puzzles, as the exam is; or `pooled` over all moves, where long games weigh more."""
    g = [
        [
            m.move is not None and m.optimal for m in x.moves
        ]  # an error is not optimal, as on the exam
        for x in games[(player, "compass", condition)].values()
    ]
    return statistics.mean(
        [m for x in g for m in x] if pooled else [statistics.mean(x) for x in g if x]
    )


def exam_tables(games: dict, exam: dict) -> None:
    rows, changes = [], []
    for player, (name, _) in PLAYERS.items():
        for condition in ["map"] if player in BASELINES else INPUTS:
            if (player, condition) not in exam:
                continue
            answers = [a for v in exam[(player, condition)].values() for a in v]
            rows.append(
                [name, INPUTS[condition], len(answers), exam_rate(exam[(player, condition)])]
            )
            rows[-1] += [statistics.mean(a[1] for a in answers if a[0] == kind) for kind in KINDS]
            rows[-1] += [in_game_optimal(games, player, condition)]
            rows[-1] += [in_game_optimal(games, player, condition, pooled=True), "", ""]
            p = [a[2] for a in answers if a[2] is not None and player in MODELS]
            if p:  # calibration, for the models that return probabilities
                optimal = [a[1] for a in answers if a[2] is not None]
                rows[-1][-2:] = [statistics.mean(p), metrics.expected_calibration_error(p, optimal)]
        if player in MODELS and (player, "map") in exam:
            full, alone = exam[(player, "everything")], exam[(player, "map")]
            mean = {
                k: statistics.mean(a[1] for a in full[k]) - statistics.mean(a[1] for a in alone[k])
                for k in full
            }
            changes.append([name, estimate(list(mean.values()))])
    header = ["Model", "Condition", "Answers", "Exam optimal rate"]
    header += [*KINDS, "Own games optimal rate"]
    write_table("exam", [*header, "Own games, every move equal", "Mean p(chosen)", "ECE"], rows)
    write_table("exam_inputs", ["Model", "Full context - map only, exam optimal rate"], changes)
    rows = []  # paired differences between the three models the paper calls similar
    for a, b in [
        ("jev", "gemma-4-26b"),
        ("jev", "deepseek-v4.1-flash"),
        ("gemma-4-26b", "deepseek-v4.1-flash"),
    ]:
        for c in INPUTS:
            x, y = exam[(a, c)], exam[(b, c)]
            optimal = [
                statistics.mean(v[1] for v in x[k]) - statistics.mean(v[1] for v in y[k]) for k in x
            ]
            won = change(games[(a, "compass", c)], games[(b, "compass", c)], "won")
            rows.append([f"{MODELS[a][0]} - {MODELS[b][0]}", INPUTS[c], won, estimate(optimal)])
    write_table(
        "pairs",
        ["Pair", "Condition", "Success rate difference", "Exam optimal-rate difference"],
        rows,
    )


def calibration_moves(games: dict, player: str) -> tuple[list, list, float, float | str]:
    """Compass moves with probabilities: p(chosen), whether the move was optimal (any tied
    best move counts), the share of those moves that had more than one best move, and the
    largest gap between a returned `confidence` and (p_max - 1/n) / (1 - 1/n) ("" if none)."""
    moves = [
        m
        for (p, r, _), v in games.items()
        if p == player and r == "compass"
        for x in v.values()
        for m in x.moves
        if m.probabilities and m.move in m.probabilities
    ]
    confidence = [min(1.0, max(0.0, m.probabilities[m.move])) for m in moves]
    ties = sum(len(m.best_moves) > 1 for m in moves) / len(moves) if moves else 0.0
    rescaled = [(m.confidence, metrics.rescaled_top(m.probabilities)) for m in moves]
    gap = max((abs(c - r) for c, r in rescaled if c is not None), default="")
    return confidence, [m.optimal for m in moves], ties, gap


def hypotheses(games: dict) -> list[list]:
    """H1-H7 of 23 September, about Jev under compass rules, checked as written (paper App. B)."""
    jev = {c: v for (p, r, c), v in games.items() if p == "jev" and r == "compass"}
    base = {p: games[(p, "compass", "map")] for p in BASELINES}
    rows: list[list] = []

    def add(statement: str, observed: str, *parts: bool) -> None:
        rows.append(
            [statement, observed, "yes" if all(parts) else "partly" if any(parts) else "no"]
        )

    def fmt(e: tuple) -> str:
        return f"{e[0]:+.2f} [{e[1]:+.2f}, {e[2]:+.2f}]"

    def mean(condition: str, field: str = "progress") -> float:
        return statistics.mean(getattr(x, field) for x in jev[condition].values())

    vs = {(p, f): change(jev["map"], base[p], f) for p in base for f in ["won", "progress"]}
    pairs = [(p, f) for p in ["random", "greedy-walls"] for f in ["won", "progress"]]
    observed = "; ".join(
        f"{'success rate' if f == 'won' else f} vs {PLAYERS[p][0]}: {fmt(vs[(p, f)])}"
        for p, f in pairs
    )
    unclear = any(
        vs[("greedy-walls", f)][1] < 0 < vs[("greedy-walls", f)][2] for f in ["won", "progress"]
    )
    add(
        "H1: under map only, Jev beats random but not greedy (walls), on won rate and progress",
        observed + ("; the comparison with Greedy (walls) is inconclusive" if unclear else ""),
        all(vs[("random", f)][1] > 0 for f in ["won", "progress"]),
        all(vs[("greedy-walls", f)][2] <= 0 for f in ["won", "progress"]),
    )

    planning = {p for p, x in base["greedy-walls"].items() if not x.won}
    slopes = [
        metrics.slope(*zip(*[(x.level, x.won) for x in v.values()], strict=True))
        for v in jev.values()
    ]
    best = max(jev, key=lambda c: statistics.mean(jev[c][p].won for p in planning))
    best_rate = statistics.mean(jev[best][p].won for p in planning)
    add(
        "H2: Jev's wins fall with the level; no condition wins half of the planning puzzles",
        f"success falls by {-max(slopes):.3f} to {-min(slopes):.3f} per route step (all 10 "
        f"conditions); planning puzzles: the {len(planning)} Greedy (walls) loses; the best "
        f"condition on them wins {best_rate:.2f} ({condition_name(best)})",
        max(slopes) < 0,
        best_rate < 0.5,
    )

    added = {c: mean(f"map+{c}") for c in COMPONENTS}
    removed = {c: mean(f"everything-{c}") for c in COMPONENTS}
    ranked, worst = sorted(added, key=added.get, reverse=True), min(removed, key=removed.get)
    add(
        "H3: simulated action outcomes help most (best map+X, worst everything-X, on progress)",
        f"progress, map + one component: "
        f"{', '.join(f'{COMPONENTS[c]} {added[c]:.2f}' for c in ranked)}; lowest full context "
        f"minus one: {condition_name(f'everything-{worst}')} {removed[worst]:.2f}",
        ranked[0] == "lookahead",
        worst == "lookahead",
    )

    def subgoal_gain(levels) -> float:
        gain = [jev["map+subgoal"][p].progress - x.progress for p, x in jev["map"].items()]
        return statistics.mean(
            g for g, x in zip(gain, jev["map"].values(), strict=True) if x.level in levels
        )

    high, low = subgoal_gain(range(3, 100)), subgoal_gain(range(1, 3))
    add(
        "H4: explicit subgoal is second among additions, and helps mostly from level 3 up",
        f"ranks {ranked.index('subgoal') + 1} of 4; "
        f"progress gain {high:+.2f} at levels 3 and up, {low:+.2f} at levels 1-2",
        ranked[1] == "subgoal",
        high > low,
    )

    memory = change(jev["map+memory"], jev["map"], "progress")
    add(
        "H5: interaction history alone adds almost nothing (within 0.05 progress of map)",
        f"progress change {fmt(memory)}",
        abs(memory[0]) <= 0.05,
    )

    wins, top = sum(x.won for x in jev["everything"].values()), max(jev, key=mean)
    add(
        "H6: full context has the best progress of the ten conditions and wins at least 28/100",
        f"best progress: {condition_name(top)} ({mean(top):.2f}); full context wins {wins}/100",
        top == "everything",
        wins >= 28,
    )

    confidence, optimal, *_ = calibration_moves(
        {k: v for k, v in games.items() if k[0] == "jev"}, "jev"
    )
    sure = [o for c, o in zip(confidence, optimal, strict=True) if c >= 0.9]
    rest = [o for c, o in zip(confidence, optimal, strict=True) if c < 0.9]
    rates = [b[1] for b in metrics.calibration_bins(confidence, optimal) if b[2] >= 30]
    add(
        "H7: Jev is overconfident, but its p(chosen) still ranks its moves",
        f"chosen move's mean probability {statistics.mean(confidence):.2f}, but "
        f"{statistics.mean(optimal):.2f} of chosen moves optimal; optimal at probability 0.9 "
        f"or more: {statistics.mean(sure):.2f} ({len(sure)} moves), below 0.9: "
        f"{statistics.mean(rest):.2f}; yet a higher-probability bin is not always more often "
        "optimal",
        statistics.mean(confidence) > statistics.mean(optimal),
        statistics.mean(sure) > statistics.mean(rest) and rates == sorted(rates),
    )
    return rows


def save(fig, name: str) -> None:
    for suffix in ["png", "pdf"]:
        metadata = {"CreationDate": None} if suffix == "pdf" else {}  # same bytes on every run
        fig.savefig(OUT / f"{name}.{suffix}", dpi=200, bbox_inches="tight", metadata=metadata)
    plt.close(fig)


def input_legend(fig, y: float) -> None:
    handles = [
        Patch(color="0.5", alpha=0.35, label="map only"),
        Patch(color="0.5", label="full context"),
    ]
    fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, y),
        ncol=3,
        frameon=False,
    )


def bar_panel(ax, players: list[str], value, xlabel: str) -> None:
    """One bar per player and input (map pale, full context dark) with its interval."""
    for y, player in enumerate(reversed(players)):
        conditions = ["map"] if player in BASELINES else list(INPUTS)
        for i, condition in enumerate(conditions):
            v, low, high = value(player, condition)
            y_bar = y + (0 if len(conditions) == 1 else (0.2 if i == 0 else -0.2))
            pale = condition == "map" and player in MODELS
            height = 0.38 if len(conditions) > 1 else 0.5
            ax.barh(y_bar, v, height=height, color=PLAYERS[player][1], alpha=0.35 if pale else 1)
            ax.errorbar(v, y_bar, xerr=[[v - low], [high - v]], color="black", lw=0.8, capsize=2)
    ax.set_xlim(0, 1)
    ax.set_xlabel(xlabel)
    ax.set_yticks(range(len(players)), [PLAYERS[p][0] for p in reversed(players)])


def fig_main(games: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 4.2), sharey=True)
    players = [p for p in PLAYERS if (p, "compass", "map") in games]
    for ax, field, label in zip(
        axes, ["won", "progress"], ["Success rate", "Progress"], strict=True
    ):

        def value(player, condition, field=field):
            return estimate(
                [getattr(x, field) for x in games[(player, "compass", condition)].values()]
            )

        bar_panel(ax, players, value, f"{label}, compass rules")
    input_legend(fig, 0.0)
    save(fig, "fig_main")


def fig_components(games: dict) -> None:
    fig, axes = plt.subplots(2, 4, figsize=(9, 5.2), sharex=True, sharey=True)
    with (OUT / "components.csv").open(encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    labels = list(COMPONENTS.values())
    for ax, (name, color) in zip(axes.flat, MODELS.values(), strict=False):
        for row in rows:
            if row["Model"] != name:
                continue
            added = row["Direction"].startswith("added")
            y = len(labels) - 1 - labels.index(row["Component"]) + (0.15 if added else -0.15)
            value, low, high = (
                float(row[f"Success rate change{s}"]) for s in ["", " low", " high"]
            )
            ax.errorbar(
                value,
                y,
                xerr=[[value - low], [high - value]],
                color=color,
                lw=1,
                capsize=2,
                marker="o" if added else "s",
                markersize=5,
                markerfacecolor=color if float(row["Holm p"]) < 0.05 else "white",
            )
        ax.axvline(0, color="0.6", lw=0.8)
        ax.set_title(textwrap.fill(name, 20), fontsize=10)
        ax.set_yticks(range(len(labels)), [textwrap.fill(label, 16) for label in reversed(labels)])
        ax.tick_params(labelbottom=True)
    axes.flat[-1].axis("off")
    mark = lambda m, f="0.3": plt.Line2D([], [], c="0.3", marker=m, ls="", mfc=f)  # noqa: E731
    shapes = [mark("o"), mark("s"), (mark("o"), mark("s")), (mark("o", "w"), mark("s", "w"))]
    texts = ["added to map only", "full context vs. full\ncontext minus it", "significant"]
    tuples = {tuple: HandlerTuple(ndivide=None)}
    axes.flat[-1].legend(shapes, [*texts, "not significant"], handler_map=tuples, frameon=False)
    fig.subplots_adjust(hspace=0.6)
    fig.supxlabel("Change in success rate when the component is included (compass)", fontsize=10)
    save(fig, "fig_components")


def fig_lines(games: dict, name: str, xs: list, key, xlabel: str) -> None:
    """Success rate per model along xs; one panel per condition."""
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.2), sharey=True)
    for ax, condition in zip(axes, INPUTS, strict=True):
        for player, (label, color) in PLAYERS.items():
            points = [(i, key(games, player, x, condition)) for i, x in enumerate(xs)]
            points = [(i, v) for i, v in points if v is not None]
            if len(points) > 1 and player != "solver":
                style = "o--" if player in BASELINES else "o-"
                ax.plot(*zip(*points, strict=True), style, ms=3, color=color, label=label)
        ax.set_xticks(
            range(len(xs)),
            [
                f"{x}".replace("up-to-", "up-to-\n") + (f"\n({RULES[x]})" if x in RULES else "")
                for x in xs
            ],
        )
        ax.set_title(INPUTS[condition], fontsize=10)
        ax.set_ylim(0, 1)
        ax.tick_params(axis="x", labelsize=8)
        ax.set_xlabel(xlabel)
    axes[0].set_ylabel("Success rate")
    handles, labels = axes[1].get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.1),
        ncol=4,
        frameon=False,
        title="dashed: baselines" if name == "fig_levels" else None,
    )
    save(fig, name)


def rules_won(games, player, rules, condition):
    g = games.get((player, rules, condition)) if player in MODELS else None  # models only
    return statistics.mean(x.won for x in g.values()) if g else None


def level_won(games, player, level, condition):
    g = games.get((player, "compass", condition if player in MODELS else "map"))
    won = [x.won for x in g.values() if x.level == level] if g else []
    return statistics.mean(won) if won else None


def fig_calibration(games: dict) -> None:
    fig, ax = plt.subplots(figsize=(4.6, 3.6))
    ax.plot([0, 1], [0, 1], color="0.6", ls=":", lw=1)
    for player, (name, color) in MODELS.items():
        confidence, optimal, *_ = calibration_moves(games, player)
        bins = [b for b in metrics.calibration_bins(confidence, optimal) if b[2] >= 30]
        if bins:
            ax.plot(*zip(*[b[:2] for b in bins], strict=True), "o-", ms=3, color=color, label=name)
    ax.set_xlabel("Probability of the chosen move (compass)")
    ax.set_ylabel("Share of chosen moves that were optimal")
    ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False)
    save(fig, "fig_calibration")


def main() -> None:
    plt.rcParams.update(
        {"font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42}
    )
    OUT.mkdir(exist_ok=True)
    for old in OUT.iterdir():
        old.unlink()
    games: dict[tuple, dict[str, Game]] = defaultdict(dict)
    for game in load_games():
        games[(game.player, game.rules, game.condition)][game.puzzle] = game
    tables(games)
    fig_main(games)
    fig_components(games)
    fig_lines(games, "fig_action_spaces", list(RULES), rules_won, "Move rules (options per move)")
    levels = sorted({x.level for x in games[("solver", "compass", "map")].values()})
    xlabel = "Level (steps to the goal; not to scale)"
    fig_lines(games, "fig_levels", levels, level_won, xlabel)
    fig_calibration(games)
    exam = load_exam()
    exam_tables(games, exam)
    print(f"{sum(len(v) for v in games.values())} games; outputs in {OUT}")


if __name__ == "__main__":
    main()

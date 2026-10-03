"""Leaderboard: entries from submitted core runs, and the table and page built from them."""

from __future__ import annotations

import html
import json
import random
import re
from collections import defaultdict
from collections.abc import Collection, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from system_one_control.bench import GameRecord, load, save, stamp, validate_file
from system_one_control.puzzles import load_puzzles

LEADERBOARD_DIR = Path(__file__).resolve().parents[2] / "leaderboard"
CORE_CONDITIONS = ("map", "everything")

KINDS = ("baseline", "chat", "decision")
REPO = "https://github.com/Exemocaro/JevStuff"
BASELINES = ("random", "greedy", "greedy-walls", "solver")


def interval(values: dict[str, float], seed: int = 0, draws: int = 1000) -> tuple[float, float]:
    """The 95% puzzle-bootstrap interval of the mean over puzzles."""
    rng = random.Random(seed)
    names = list(values)
    means = sorted(sum(values[rng.choice(names)] for _ in names) / len(names) for _ in range(draws))
    return means[int(0.025 * draws)], means[int(0.975 * draws)]


def condition_stats(
    records: Sequence[GameRecord],
) -> dict[str, dict[str, tuple[float, float, float]]]:
    """Per condition: won, progress and SPL means with their bootstrap intervals."""
    by_condition: dict[str, list[GameRecord]] = defaultdict(list)
    for record in records:
        by_condition[record.condition].append(record)
    stats: dict[str, dict[str, tuple[float, float, float]]] = {}
    for condition, group in by_condition.items():
        won = {r.puzzle: float(r.won) for r in group}
        progress = {r.puzzle: r.progress for r in group}
        spl = {r.puzzle: r.fewest_moves / len(r.moves) if r.won else 0.0 for r in group}
        stats[condition] = {
            name: (sum(values.values()) / len(values), *interval(values))
            for name, values in (("won", won), ("progress", progress), ("spl", spl))
        }
    return stats


def core_scope(puzzles: Collection[str], player: str) -> list[tuple[str, str, str, str]]:
    """The expected core games: every puzzle x map+everything x player, compass rules."""
    return [
        (puzzle, condition, player, "compass")
        for puzzle in sorted(puzzles)
        for condition in CORE_CONDITIONS
    ]


def submit(
    files: Sequence[Path],
    *,
    name: str,
    org: str,
    url: str,
    notes: str,
    player: str | None = None,
    kind: str | None = None,
    day: str | None = None,
    leaderboard: Path = LEADERBOARD_DIR,
) -> Path:
    """Validate core-track files and write the player's entry and core games. Returns its path."""
    records = [record for path in files for record in load(path)]
    players = {record.player for record in records}
    if player is None:
        if len(players) != 1:
            raise ValueError(f"one player per submission, got: {', '.join(sorted(players))}")
        player = next(iter(players))
    if not re.fullmatch(r"[a-z0-9._-]+", player):
        raise ValueError(f"player names use [a-z0-9._-], not {player!r}")
    records = [record for record in records if record.player == player]
    if any(record.rules != "compass" for record in records):
        raise ValueError("only compass records go on the core leaderboard")
    seen = [(r.puzzle, r.condition, r.player, r.rules) for r in records]
    if len(set(seen)) != len(seen):
        raise ValueError("duplicate games in the submission")
    failures = [f for path in files for f in validate_file(path)]
    missing = sorted(set(core_scope(set(load_puzzles()), player)) - set(seen))
    failures += [f"missing game {key}" for key in missing]
    if failures:
        raise ValueError("submission does not validate:\n" + "\n".join(failures))
    if kind is None:
        if player not in BASELINES:
            raise ValueError(f"pass --kind for {player!r}; known: {', '.join(KINDS)}")
        kind = "baseline"
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; known: {', '.join(KINDS)}")
    if kind == "baseline" and player not in BASELINES:
        raise ValueError(f"only {', '.join(BASELINES)} are baselines, not {player!r}")
    core = [r for r in records if r.condition in CORE_CONDITIONS]
    stamp_of = next((r.benchmark for r in core if r.benchmark is not None), None)
    stamp_of = stamp_of or stamp()
    costs = [m.cost for r in core for m in r.moves if m.cost is not None]
    waits = [m.seconds for r in core for m in r.moves if m.seconds is not None]
    results = leaderboard / "results" / f"{player}.jsonl"
    results.parent.mkdir(parents=True, exist_ok=True)
    save(core, results)
    entry = {
        "name": name,
        "player": player,
        "org": org,
        "url": url,
        "notes": notes,
        "kind": kind,
        "benchmark": stamp_of,
        "track": "core",
        "results": results.name,
        "conditions": condition_stats(core),
        "cost": round(sum(costs), 4) if costs else None,
        "latency": round(sorted(waits)[len(waits) // 2], 2) if waits else None,
        "date": day or date.today().isoformat(),
    }
    (leaderboard / "entries").mkdir(parents=True, exist_ok=True)
    path = leaderboard / "entries" / f"{player}.json"
    path.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8", newline="")
    return path


def safe(text: str) -> str:
    """Entry text safe for the markdown table: no pipes or newlines."""
    return text.replace("|", "/").replace("\n", " ")


def ranked(entries: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Entries sorted by everything progress, best first."""
    return sorted(entries, key=lambda e: e["conditions"]["everything"]["progress"][0], reverse=True)


def shown(value: float | None, kind: str) -> str:
    """A cost or latency for the table: n/a when unreported, 0 for a baseline, else the number."""
    if value is None:
        return "0" if kind == "baseline" else "n/a"
    return f"{value:g}"


LEGEND = """- **everything / map**: the core track conditions (compass rules, 100 puzzles each);
  `everything` is the full context.
- **won**: share of the 100 puzzles where the goal was reached before the move limit.
- **progress**: how close a game got to the goal at its closest point (1 for a win).
- **SPL**: fewest moves over moves used for a won game, 0 for a lost one.
- **[lo-hi]**: 95% bootstrap interval over puzzles.
- **cost**: USD for one core run (200 games), as reported by the player; n/a means not reported.
- **latency**: median seconds per answer (the successful call alone).
- **kind**: baseline, chat model or decision model.

How to submit: [SUBMITTING.md](../SUBMITTING.md).
"""


def player_cell(entry: dict[str, Any]) -> str:
    """The markdown player cell: a link for clean http(s) urls, else escaped text."""
    name = html.escape(safe(entry["name"]))
    url = entry["url"]
    if page_url(url) and not any(mark in url for mark in ("(", ")", " ", '"')):
        return f"[{name}]({url})"
    return name


def build_table(entries: Sequence[dict[str, Any]]) -> str:
    """The core leaderboard as markdown, sorted by everything progress."""
    header = [
        "player",
        "org",
        "kind",
        "everything won",
        "everything progress",
        "everything SPL",
        "map won",
        "map progress",
        "map SPL",
        "cost",
        "latency",
        "notes",
    ]
    lines = ["|" + "|".join(header) + "|", "|" + "|".join(["---"] * len(header)) + "|"]
    for entry in ranked(entries):
        row = [player_cell(entry), html.escape(safe(entry["org"])), entry["kind"]]
        for condition in ("everything", "map"):
            for metric in ("won", "progress", "spl"):
                mean, lo, hi = entry["conditions"][condition][metric]
                row.append(f"{mean:.2f} [{lo:.2f}-{hi:.2f}]")
        row += [shown(entry["cost"], entry["kind"]), shown(entry["latency"], entry["kind"])]
        row.append(html.escape(safe(entry["notes"])))
        lines.append("|" + "|".join(row) + "|")
    return "\n".join(lines) + "\n"


def page_url(url: str) -> str | None:
    """The url when it points at a web page, else None."""
    return url if url.startswith(("http://", "https://")) else None


def build_page(entries: Sequence[dict[str, Any]]) -> str:
    """The leaderboard as one static page: the table plus a small sorter, light and dark."""
    rows = []
    for entry in ranked(entries):
        name = html.escape(entry["name"])
        link = page_url(entry["url"])
        player = f'<a href="{html.escape(link)}">{name}</a>' if link else name
        ev, mp = entry["conditions"]["everything"], entry["conditions"]["map"]
        cost = entry["cost"]
        rows.append(
            f"<tr><td>{player}</td><td>{html.escape(entry['org'])}</td>"
            f"<td>{html.escape(entry['kind'])}</td>"
            f'<td data-v="{ev["progress"][0]}">{ev["progress"][0]:.2f}</td>'
            f'<td data-v="{mp["progress"][0]}">{mp["progress"][0]:.2f}</td>'
            f'<td data-v="{ev["won"][0]}">{ev["won"][0]:.2f}</td>'
            f'<td data-v="{cost if cost is not None else ""}">'
            f"{shown(cost, entry['kind'])}</td>"
            f"<td>{html.escape(entry['notes'])}</td></tr>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>System-One Control Bench leaderboard</title>
<style>
:root {{ color-scheme: light dark; }}
table {{ border-collapse: collapse; }}
th, td {{ border: 1px solid gray; padding: 4px 8px; text-align: right; }}
th:first-child, td:first-child, td:nth-child(2), td:nth-child(3), td:last-child
  {{ text-align: left; }}
th {{ cursor: pointer; }}
</style>
</head>
<body>
<h1>System-One Control Bench leaderboard</h1>
<table id="board"><thead><tr>
<th>player</th><th>org</th><th>kind</th><th>everything progress</th>
<th>map progress</th><th>everything won</th><th>cost (USD)</th><th>notes</th>
</tr></thead><tbody>
{"".join(rows)}
</tbody></table>
<ul>
<li><b>everything / map</b>: the two conditions of the core track (compass rules, 100 puzzles each);
<b>everything</b> is the full context.</li>
<li><b>won</b>: share of puzzles where the goal was reached before the move limit.</li>
<li><b>progress</b>: how close a game got to the goal at its closest point (1 for a win).</li>
<li><b>cost</b>: USD for one core run (200 games), as reported by the player;
n/a means not reported.</li>
<li><b>kind</b>: baseline, chat model or decision model. Click a header to sort.</li>
<li>Intervals, SPL and latency (median seconds per answer) are in the
<a href="{REPO}/blob/main/leaderboard/README.md">full table</a>.</li>
</ul>
<p>How to submit: <a href="{REPO}/blob/main/SUBMITTING.md">SUBMITTING.md</a>.</p>
<script>
document.querySelectorAll("th").forEach((h, i) => h.addEventListener("click", () => {{
  const rows = [...document.querySelectorAll("#board tbody tr")];
  rows.sort((a, b) => {{
    const x = a.children[i].dataset.v ?? a.children[i].textContent;
    const y = b.children[i].dataset.v ?? b.children[i].textContent;
    if (x === "" || y === "") return x === "" ? 1 : -1;
    return isNaN(x) ? x.localeCompare(y) : x - y;
  }});
  document.querySelector("#board tbody").append(...rows);
}}));
</script>
</body>
</html>
"""


def rebuild(leaderboard: Path = LEADERBOARD_DIR, docs: Path | None = None) -> tuple[Path, Path]:
    """Recompute every entry from leaderboard/results/ and rebuild the table and page."""
    entries = []
    for path in sorted((leaderboard / "entries").glob("*.json")):
        meta = json.loads(path.read_text(encoding="utf-8"))
        if path.stem != meta["player"]:
            raise ValueError(
                f"{path.name} holds the entry for {meta['player']!r}, not its own name"
            )
        made = submit(
            [leaderboard / "results" / meta["results"]],
            name=meta["name"],
            org=meta["org"],
            url=meta["url"],
            notes=meta["notes"],
            player=meta["player"],
            kind=meta["kind"],
            day=meta["date"],
            leaderboard=leaderboard,
        )
        entries.append(json.loads(made.read_text(encoding="utf-8")))
    readme = leaderboard / "README.md"
    readme.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text(
        "# Leaderboard\n\nCore track, best everything progress first.\n\n"
        + LEGEND
        + "\n"
        + build_table(entries),
        encoding="utf-8",
        newline="",
    )
    page = (docs or leaderboard.parents[0] / "docs") / "index.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(build_page(entries), encoding="utf-8", newline="")
    return readme, page

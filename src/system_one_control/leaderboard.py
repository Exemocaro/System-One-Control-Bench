"""Leaderboard: entries from submitted core runs, and the table and page built from them."""

from __future__ import annotations

import html
import json
import random
from collections import defaultdict
from collections.abc import Collection, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from system_one_control.bench import GameRecord, load, save, stamp, validate_file
from system_one_control.puzzles import load_puzzles

LEADERBOARD_DIR = Path(__file__).resolve().parents[2] / "leaderboard"
CORE_CONDITIONS = ("map", "everything")

KINDS = ("baseline", "local", "chat", "bounded decision")
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
    puzzles: Collection[str] | None = None,
    leaderboard: Path = LEADERBOARD_DIR,
) -> Path:
    """Validate core-track files and write the player's entry and core games. Returns its path."""
    records = [record for path in files for record in load(path)]
    players = {record.player for record in records}
    if player is None:
        if len(players) != 1:
            raise ValueError(f"one player per submission, got: {', '.join(sorted(players))}")
        player = next(iter(players))
    records = [record for record in records if record.player == player]
    if any(record.rules != "compass" for record in records):
        raise ValueError("only compass records go on the core leaderboard")
    seen = [(r.puzzle, r.condition, r.player, r.rules) for r in records]
    if len(set(seen)) != len(seen):
        raise ValueError("duplicate games in the submission")
    if puzzles is None:
        puzzles = set(load_puzzles())
    failures = [f for path in files for f in validate_file(path)]
    missing = sorted(set(core_scope(puzzles, player)) - set(seen))
    failures += [f"missing game {key}" for key in missing]
    if failures:
        raise ValueError("submission does not validate:\n" + "\n".join(failures))
    if kind is None:
        if player not in BASELINES:
            raise ValueError(f"pass --kind for {player!r}; known: {', '.join(KINDS)}")
        kind = "baseline"
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; known: {', '.join(KINDS)}")
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
        "puzzles": sorted({r.puzzle for r in core}),
        "conditions": condition_stats(core),
        "cost": round(sum(costs), 4) if costs else None,
        "latency": round(sorted(waits)[len(waits) // 2], 2) if waits else None,
        "date": day or date.today().isoformat(),
    }
    (leaderboard / "entries").mkdir(parents=True, exist_ok=True)
    path = leaderboard / "entries" / f"{player}.json"
    path.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    return path


def safe(text: str) -> str:
    """Entry text safe for the markdown table: no pipes or newlines."""
    return text.replace("|", "/").replace("\n", " ")


def ranked(entries: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Entries sorted by everything progress, best first."""
    return sorted(entries, key=lambda e: e["conditions"]["everything"]["progress"][0], reverse=True)


def build_table(entries: Sequence[dict[str, Any]]) -> str:
    """The core leaderboard as markdown, sorted by everything progress."""
    header = [
        "player",
        "everything won",
        "everything progress",
        "everything SPL",
        "map won",
        "map progress",
        "map SPL",
        "cost",
        "latency",
    ]
    lines = ["|" + "|".join(header) + "|", "|" + "|".join(["---"] * len(header)) + "|"]
    for entry in ranked(entries):
        name = safe(entry["name"])
        row = [f"[{name}]({safe(entry['url'])})" if entry["url"] else name]
        for condition in ("everything", "map"):
            for metric in ("won", "progress", "spl"):
                mean, lo, hi = entry["conditions"][condition][metric]
                row.append(f"{mean:.2f} [{lo:.2f}-{hi:.2f}]")
        row += [str(entry["cost"] or "-"), str(entry["latency"] or "-")]
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
            f"<tr><td>{player}</td><td>{html.escape(entry['kind'])}</td>"
            f'<td data-v="{ev["progress"][0]}">{ev["progress"][0]:.2f}</td>'
            f'<td data-v="{mp["progress"][0]}">{mp["progress"][0]:.2f}</td>'
            f'<td data-v="{ev["won"][0]}">{ev["won"][0]:.2f}</td>'
            f'<td data-v="{cost if cost is not None else ""}">'
            f"{cost if cost is not None else '-'}</td></tr>"
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
th:first-child, td:first-child, td:nth-child(2) {{ text-align: left; }}
th {{ cursor: pointer; }}
</style>
</head>
<body>
<h1>System-One Control Bench leaderboard</h1>
<table id="board"><thead><tr>
<th>player</th><th>kind</th><th>everything progress</th>
<th>map progress</th><th>everything won</th><th>cost</th>
</tr></thead><tbody>
{"".join(rows)}
</tbody></table>
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
        made = submit(
            [leaderboard / "results" / meta["results"]],
            name=meta["name"],
            org=meta["org"],
            url=meta["url"],
            notes=meta["notes"],
            player=meta["player"],
            kind=meta["kind"],
            day=meta["date"],
            puzzles=set(meta["puzzles"]),
            leaderboard=leaderboard,
        )
        entries.append(json.loads(made.read_text(encoding="utf-8")))
    readme = leaderboard / "README.md"
    readme.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text(
        "# Leaderboard\n\nCore track, best everything progress first.\n\n" + build_table(entries),
        encoding="utf-8",
    )
    page = (docs or leaderboard.parents[0] / "docs") / "index.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(build_page(entries), encoding="utf-8")
    return readme, page

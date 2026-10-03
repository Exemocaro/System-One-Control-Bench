"""Leaderboard: entries from submitted core runs, and the table and page built from them."""

from __future__ import annotations

import json
import random
import shutil
from collections import defaultdict
from collections.abc import Collection, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from system_one_control.bench import GameRecord, load, stamp, validate_file
from system_one_control.players import PLAYERS, make_player
from system_one_control.players.baselines import (
    GreedyPlayer,
    RandomPlayer,
    SolverPlayer,
    WallAwareGreedyPlayer,
)
from system_one_control.players.local import GLiClassPlayer, LayaPlayer, LocalLLMPlayer
from system_one_control.players.remote import LLMPlayer
from system_one_control.puzzles import load_puzzles

LEADERBOARD_DIR = Path(__file__).resolve().parents[2] / "leaderboard"
CORE_CONDITIONS = ("map", "everything")

KINDS = ("baseline", "local", "chat", "bounded decision")


def kind_of(name: str) -> str:
    """What leaderboard kind a registry player is."""
    player = make_player(name)
    if isinstance(player, (RandomPlayer, GreedyPlayer, WallAwareGreedyPlayer, SolverPlayer)):
        return "baseline"
    if isinstance(player, (LayaPlayer, GLiClassPlayer, LocalLLMPlayer)):
        return "local"
    if isinstance(player, LLMPlayer):
        return "chat"
    return "bounded decision"


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
    puzzles: Collection[str] | None = None,
    leaderboard: Path = LEADERBOARD_DIR,
) -> Path:
    """Validate core-track files and write the player's leaderboard entry. Returns its path."""
    records = [record for path in files for record in load(path)]
    players = {record.player for record in records}
    if player is None:
        if len(players) != 1:
            raise ValueError(f"one player per submission, got: {', '.join(sorted(players))}")
        player = next(iter(players))
    records = [record for record in records if record.player == player]
    if puzzles is None:
        puzzles = set(load_puzzles())
    have = {(r.puzzle, r.condition, r.player, r.rules) for r in records}
    failures = [f for path in files for f in validate_file(path)]
    missing = sorted(set(core_scope(puzzles, player)) - have)
    failures += [f"missing game {key}" for key in missing]
    if failures:
        raise ValueError("submission does not validate:\n" + "\n".join(failures))
    kind = kind or (kind_of(player) if player in PLAYERS else None)
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; known: {', '.join(KINDS)}")
    stamp_of = next((r.benchmark for r in records if r.benchmark is not None), None)
    stamp_of = stamp_of or stamp()
    costs = [m.cost for r in records for m in r.moves if m.cost is not None]
    waits = [m.seconds for r in records for m in r.moves if m.seconds is not None]
    entry = {
        "name": name,
        "player": player,
        "org": org,
        "url": url,
        "notes": notes,
        "kind": kind,
        "benchmark": stamp_of,
        "track": "core",
        "conditions": condition_stats([r for r in records if r.condition in CORE_CONDITIONS]),
        "cost": round(sum(costs), 4) if costs else None,
        "latency": round(sorted(waits)[len(waits) // 2], 2) if waits else None,
        "date": date.today().isoformat(),
    }
    (leaderboard / "entries").mkdir(parents=True, exist_ok=True)
    (leaderboard / "results").mkdir(parents=True, exist_ok=True)
    path = leaderboard / "entries" / f"{player}.json"
    path.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    for source in files:
        shutil.copy(source, leaderboard / "results" / source.name)
    return path


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
        row = [f"[{entry['name']}]({entry['url']})" if entry["url"] else entry["name"]]
        for condition in ("everything", "map"):
            for metric in ("won", "progress", "spl"):
                mean, lo, hi = entry["conditions"][condition][metric]
                row.append(f"{mean:.2f} [{lo:.2f}-{hi:.2f}]")
        row += [str(entry["cost"] or "-"), str(entry["latency"] or "-")]
        lines.append("|" + "|".join(row) + "|")
    return "\n".join(lines) + "\n"


def build_page(entries: Sequence[dict[str, Any]]) -> str:
    """The leaderboard as one static page: a sortable table, light and dark."""
    data = json.dumps(sorted(entries, key=lambda e: e["name"]))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>System-One Control Bench leaderboard</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2em auto; padding: 0 1em; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid gray; padding: 4px 8px; text-align: right; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ cursor: pointer; }}
</style>
</head>
<body>
<h1>System-One Control Bench leaderboard</h1>
<table id="board"><thead><tr>
<th data-k="name">player</th><th data-k="progress">everything progress</th>
<th data-k="map">map progress</th><th data-k="won">everything won</th><th data-k="cost">cost</th>
</tr></thead><tbody></tbody></table>
<script>
const entries = {data};
const body = document.querySelector("#board tbody");
let key = "progress", down = true;
function cell(e, k) {{
  if (k === "name") return e.url ? `<a href="${{e.url}}">${{e.name}}</a>` : e.name;
  if (k === "cost") return e.cost ?? "-";
  if (k === "map") return e.conditions.map.progress[0].toFixed(2);
  if (k === "won") return e.conditions.everything.won[0].toFixed(2);
  return e.conditions.everything.progress[0].toFixed(2);
}}
function render() {{
  const rows = [...entries].sort((a, b) => {{
    const x = cell(a, key), y = cell(b, key);
    return (isNaN(x) ? x.localeCompare(y) : x - y) * (down ? -1 : 1);
  }});
  let html = "";
  for (const e of rows)
    html += `<tr><td>${{cell(e, "name")}}</td><td>${{cell(e, "progress")}}</td>` +
      `<td>${{cell(e, "map")}}</td><td>${{cell(e, "won")}}</td><td>${{cell(e, "cost")}}</td></tr>`;
  body.innerHTML = html;
}}
document.querySelectorAll("th").forEach(h => h.addEventListener("click", () => {{
  if (h.dataset.k === key) down = !down; else {{ key = h.dataset.k; down = true; }}
  render();
}}));
render();
</script>
</body>
</html>
"""


def rebuild(leaderboard: Path = LEADERBOARD_DIR, docs: Path | None = None) -> tuple[Path, Path]:
    """Rebuild the leaderboard README and page from the entries. Returns both paths."""
    entries = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((leaderboard / "entries").glob("*.json"))
    ]
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

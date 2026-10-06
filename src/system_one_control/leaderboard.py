"""Leaderboard: entries from submitted core runs, and the table and page built from them."""

from __future__ import annotations

import html
import json
import math
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
REPO = "https://github.com/Exemocaro/System-One-Control-Bench"
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


LEGEND = """- **everything / map**: the two conditions of the core track, compass rules (one step
  per move), 100 puzzles each. `everything` is the full context; `map` is the map only.
- **won**: share of the 100 puzzles where the goal was reached before the move limit.
- **progress**: how close a game got to the goal at its closest point (1 for a win).
- **SPL**: fewest moves over moves used for a won game, 0 for a lost one.
- **[lo-hi]**: 95% interval: how much the score depends on which puzzles are in the set
  (puzzles redrawn at random 1,000 times; the report uses 10,000, so the ends can differ by 0.01).
- **cost**: USD for one core run (200 games), as reported by the player, rounded up to the
  cent; n/a means not reported.
- **latency**: median seconds per answer (the successful call alone).
- **kind**: baseline, chat model or decision model.

The website version of this table: https://exemocaro.github.io/System-One-Control-Bench/.
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
        row += [dollars(entry["cost"], entry["kind"]), shown(entry["latency"], entry["kind"])]
        row.append(html.escape(safe(entry["notes"])))
        lines.append("|" + "|".join(row) + "|")
    return "\n".join(lines) + "\n"


def page_url(url: str) -> str | None:
    """The url when it points at a web page, else None."""
    return url if url.startswith(("http://", "https://")) else None


def dollars(value: float | None, kind: str) -> str:
    """A cost for the page: rounded up to the cent, or as `shown` when there is none."""
    if value is None:
        return shown(value, kind)
    return f"{math.ceil(round(value * 100, 6)) / 100:.2f}"


CONDITION_ROWS = "\n".join(
    f"<tr><td>{name}</td><td><code>{code}</code></td><td>{added}</td></tr>"
    for name, code, added in [
        ("map only", "map", "nothing"),
        ("map + surroundings", "map+surroundings", "surroundings"),
        ("map + move history", "map+memory", "move history"),
        ("map + move outcomes", "map+lookahead", "move outcomes"),
        ("map + subgoal", "map+subgoal", "subgoal"),
        ("full context", "everything", "all four components"),
        ("full context minus surroundings", "everything-surroundings", "all but surroundings"),
        ("full context minus move history", "everything-memory", "all but move history"),
        ("full context minus move outcomes", "everything-lookahead", "all but move outcomes"),
        ("full context minus subgoal", "everything-subgoal", "all but the subgoal"),
    ]
)
RULE_ROWS = "\n".join(
    f"<tr><td><code>{rules}</code></td><td>{move}</td><td>{options}</td></tr>"
    for rules, move, options in [
        ("compass", "one step north, south, east or west (the leaderboard's rules)", 4),
        ("two-moves", "exactly two steps", 16),
        ("up-to-two-moves", "one or two steps", 20),
        ("three-moves", "exactly three steps", 64),
        ("up-to-three-moves", "one, two or three steps", 84),
    ]
)


# The recorded full-context games the page replays: results file, player and puzzle.
EXAMPLES = [
    ("jev.jsonl", "Jev", "gen-10-03"),
    ("deepseek-v4.1-flash-think.jsonl", "DeepSeek V4.1 Flash (reasoning)", "gen-20-01"),
]


def example_frames(leaderboard: Path) -> list[dict[str, Any]]:
    """Each example game: a title, and the board after each move with a note on the move."""
    puzzles, examples = load_puzzles(), []
    for results, player, name in EXAMPLES:
        path = leaderboard / "results" / results
        if not path.exists():
            continue
        games = map(json.loads, path.read_text(encoding="utf-8").splitlines())
        game = next(g for g in games if g["puzzle"] == name and g["condition"] == "everything")
        puzzle = puzzles[name]
        board, frames = puzzle.board, [{"map": puzzle.board.draw(), "note": "Start"}]
        for number, played in enumerate(game["moves"], start=1):
            move = puzzle.rules.find_move(board, played["move"])
            assert move is not None, f"{name}: move {number} is not an allowed move"
            board = puzzle.rules.apply(board, move)
            note = f"Move {number} of {len(game['moves'])}: {played['move']}"
            note += " (optimal)" if played["optimal"] else " (not optimal)"
            note += ", carrying the key" if board.holding else ""
            frames.append({"map": board.draw(), "note": note})
        examples.append({"title": f"{player}, level {puzzle.level}", "frames": frames})
    return examples


def replay_section(examples: Sequence[dict[str, Any]]) -> str:
    """Recorded games side by side, each stepped through with its own two buttons."""
    if not examples:
        return ""
    data = json.dumps(list(examples)).replace("</", "<\/")
    boxes = "".join(
        f'<div class="replay" data-game="{i}"><h3>{html.escape(game["title"])}</h3><pre></pre>'
        '<p></p><div><button aria-label="Previous move">&larr;</button>'
        '<button aria-label="Next move">&rarr;</button></div></div>'
        for i, game in enumerate(examples)
    )
    return f"""<h2>Two games, move by move</h2>
<p>Two full-context games as recorded for this leaderboard. <code>A</code> is the agent,
<code>K</code> the key, <code>D</code> the locked door, <code>G</code> the goal and <code>#</code>
a wall. Step through each game with its arrows.</p>
<div class="replays">{boxes}</div>
<script>
const games = {data};
document.querySelectorAll(".replay").forEach(box => {{
  const frames = games[box.dataset.game].frames;
  let at = 0;
  const show = step => {{
    at = Math.max(0, Math.min(frames.length - 1, at + step));
    box.querySelector("pre").textContent = frames[at].map;
    box.querySelector("p").textContent = frames[at].note;
  }};
  const [back, forward] = box.querySelectorAll("button");
  back.onclick = () => show(-1);
  forward.onclick = () => show(1);
  show(0);
}});
</script>
"""


def build_page(entries: Sequence[dict[str, Any]], examples: Sequence[dict[str, Any]] = ()) -> str:
    """The leaderboard as one static page: an introduction, the table and a small sorter."""
    rows = []
    for entry in ranked(entries):
        name = html.escape(entry["name"])
        link = page_url(entry["url"])
        player = f'<a href="{html.escape(link)}">{name}</a>' if link else name
        cells = [f"<td>{player}</td>", f"<td>{html.escape(entry['kind'])}</td>"]
        for condition in ("everything", "map"):
            for metric in ("won", "progress"):
                mean, lo, hi = entry["conditions"][condition][metric]
                text = f"{mean * 100:.0f}%" if metric == "won" else f"{mean:.2f}"
                cells.append(
                    f'<td data-v="{mean}" title="95% interval: {lo:.2f} to {hi:.2f}">{text}</td>'
                )
        cost = entry["cost"]
        cells.append(
            f'<td data-v="{cost if cost is not None else ""}">{dollars(cost, entry["kind"])}</td>'
        )
        cells.append(f"<td>{html.escape(entry['notes'])}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>System-One Control Bench</title>
<style>
:root {{ --bg: #fbfbfa; --fg: #1d1d1b; --muted: #5f5f5a; --line: #dddcd6; --head: #f0efea;
  --link: #1f5fbf; color-scheme: light; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg: #171716; --fg: #ececea; --muted: #a3a39d; --line: #34342f; --head: #22221f;
    --link: #8ab4f8; color-scheme: dark; }}
}}
body {{ background: var(--bg); color: var(--fg); margin: 0;
  font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }}
main {{ max-width: 1100px; margin: 0 auto; padding: 32px 16px 48px; }}
h1 {{ font-size: 1.8rem; margin: 0 0 12px; text-align: center; }}
h2 {{ font-size: 1.2rem; margin: 32px 0 8px; }}
a {{ color: var(--link); }}
.links {{ text-align: center; }}
.links a {{ margin: 0 8px; }}
.scroll {{ overflow-x: auto; margin: 24px 0; }}
.info th, .info td {{ text-align: left; }}
.info td:first-child {{ font-weight: normal; }}
.info td:last-child {{ color: var(--fg); min-width: 0; }}
.replays {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 24px 48px; }}
.replay {{ display: flex; flex-direction: column; align-items: center; min-width: 280px; }}
.replay h3 {{ font-size: 1rem; margin: 0; }}
.replay pre {{ display: inline-block; text-align: left; font-size: 1.3rem; line-height: 1.2;
  padding: 12px 18px; border: 1px solid var(--line); border-radius: 6px; margin: 8px 0 auto; }}
.replay button {{ font-size: 1.2rem; padding: 4px 18px; margin: 0 6px; cursor: pointer; }}
table {{ border-collapse: collapse; font-size: 0.92rem; }}
th, td {{ border-bottom: 1px solid var(--line); padding: 6px 10px; text-align: right;
  vertical-align: top; }}
th {{ background: var(--head); white-space: nowrap; }}
th[data-col] {{ cursor: pointer; }}
th[rowspan]:nth-child(-n+2), td:nth-child(-n+2), th[rowspan]:last-child, td:last-child
  {{ text-align: left; }}
th[colspan] {{ text-align: center; }}
td:first-child {{ white-space: nowrap; font-weight: 600; }}
td:last-child {{ color: var(--muted); min-width: 260px; }}
td[title] {{ font-variant-numeric: tabular-nums; }}
</style>
</head>
<body>
<main>
<h1>System-One Control Bench</h1>
<p>A model guides an agent across a small grid puzzle to a goal, one move at a time, choosing
each move from a list of options. A solver knows every best move, so every choice can be
scored exactly. The 100 puzzles range from 1 to 20 steps, and many need a key for a locked
door. The leaderboard uses compass rules (one step per move) and two conditions, map only and
full context, so each player plays 200 games.</p>
<p class="links"><a href="{REPO}/blob/main/paper/main.pdf">Report (PDF)</a>
<a href="{REPO}">Code and data</a>
<a href="{REPO}/blob/main/SUBMITTING.md">Submit a model</a>
<a href="{REPO}/blob/main/leaderboard/README.md">Full table</a></p>
<div class="scroll">
<table id="board"><thead><tr>
<th rowspan="2" data-col="0">Player</th><th rowspan="2" data-col="1">Kind</th>
<th colspan="2">Full context</th><th colspan="2">Map only</th>
<th rowspan="2" data-col="6">Cost (USD)</th><th rowspan="2">Notes</th></tr>
<tr><th data-col="2">Won</th><th data-col="3">Progress</th>
<th data-col="4">Won</th><th data-col="5">Progress</th></tr>
</thead><tbody>
{"".join(rows)}
</tbody></table>
</div>
<ul>
<li><b>Won</b>: the share of the 100 puzzles where the agent reached the goal within the move
limit (twice the fewest moves needed).</li>
<li><b>Progress</b>: how close the agent got to the goal at its closest point, from 0 (never
closer than at the start) to 1 (reached it).</li>
<li><b>Cost</b>: US dollars for the 200 games, as reported by the player, rounded up to the
cent; n/a means not reported.</li>
<li>Hover a score for its 95% interval, which shows how much it depends on the puzzles in the
set. Click a header to sort.</li>
</ul>
{replay_section(examples)}<h2>Conditions</h2>
<p>A condition sets what the player is told. Every request has the rules, the numbered map,
the agent's position, what it carries and where the key, door and goal are (map only). Four
components can be added: <b>surroundings</b> (what is next to the agent and how far away each
object is), <b>move history</b> (every move so far and what it did), <b>move outcomes</b> (each
option says what it would do) and <b>subgoal</b> (the question names the next target).</p>
<div class="scroll"><table class="info"><thead><tr><th>Condition</th><th>Name in the code</th>
<th>What is added to the map</th></tr></thead><tbody>
{CONDITION_ROWS}
</tbody></table></div>
<h2>Move rules</h2>
<p>A move is one decision. Under the sequence rules a move is several steps chosen together,
and every possible sequence is offered, including ones that walk into walls.</p>
<div class="scroll"><table class="info"><thead><tr><th>Rules</th><th>One move is</th>
<th>Options</th></tr></thead><tbody>
{RULE_ROWS}
</tbody></table></div>
</main>
<script>
document.querySelectorAll("th[data-col]").forEach(h => h.addEventListener("click", () => {{
  const i = Number(h.dataset.col);
  const rows = [...document.querySelectorAll("#board tbody tr")];
  rows.sort((a, b) => {{
    const x = a.children[i].dataset.v ?? a.children[i].textContent;
    const y = b.children[i].dataset.v ?? b.children[i].textContent;
    if (x === "" || y === "") return x === "" ? 1 : -1;
    return isNaN(x) ? x.localeCompare(y) : y - x;
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
        "# Leaderboard\n\nCore track, sorted by full-context progress, best first.\n\n"
        + LEGEND
        + "\n"
        + build_table(entries),
        encoding="utf-8",
        newline="",
    )
    page = (docs or leaderboard.parents[0] / "docs") / "index.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(build_page(entries, example_frames(leaderboard)), encoding="utf-8", newline="")
    return readme, page

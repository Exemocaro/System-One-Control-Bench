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
    """Entries sorted by full-context games won, then full-context progress, best first."""
    return sorted(
        entries,
        key=lambda e: (
            e["conditions"]["everything"]["won"][0],
            e["conditions"]["everything"]["progress"][0],
        ),
        reverse=True,
    )


def shown(value: float | None, kind: str) -> str:
    """A cost or latency for the table: n/a when unreported, 0 for a baseline, else the number."""
    if value is None:
        return "0" if kind == "baseline" else "n/a"
    return f"{value:g}"


LEGEND = """- **full context / map only**: the two conditions of the core track (`everything` and
  `map` in the code), compass rules (one step per move), 100 puzzles each.
- **won**: the share of the 100 puzzles finished within the move limit, which is twice the
  shortest route.
- **progress**: how much closer the agent got to the goal at its best point, averaged over the
  puzzles: 1 means finished, 0 means it never got closer than where it started.
- **SPL**: for a won game, the moves of the shortest route over the moves used; 0 for a lost one.
- **[lo-hi]**: 95% interval: how much the score depends on which puzzles are in the set
  (puzzles redrawn at random 1,000 times; the report uses 10,000, so the ends can differ by 0.01).
- **cost**: the reported API cost in USD for one core run (200 games), rounded up to the cent;
  n/a means no cost was reported. Local computing is not included.
- **latency**: median seconds per answer (the successful call alone).
- **kind**: baseline, chat model or decision model.

The same results as a web page, with two recorded games to step through:
https://exemocaro.github.io/System-One-Control-Bench/.
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
    """The core leaderboard as markdown, sorted by full-context games won."""
    header = [
        "player",
        "org",
        "kind",
        "full context won",
        "full context progress",
        "full context SPL",
        "map only won",
        "map only progress",
        "map only SPL",
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


COMPONENT_ROWS = "\n".join(
    f"<tr><td>{name}</td><td>{meaning}</td></tr>"
    for name, meaning in [
        ("Surroundings", "What is next to the agent, and how far away the key, door and goal are."),
        ("Move history", "Every move the player has already made, and what it did."),
        ("Move outcomes", "What would happen if the player chose each option."),
        ("Subgoal", "Which object to aim for next: the key, the door or the goal."),
    ]
)
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
    ("deepseek-v4.1-flash-think.jsonl", "DeepSeek V4.1 Flash (reasoning)", "gen-20-09"),
]


def example_games(leaderboard: Path) -> list[dict[str, Any]]:
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
        result = "won" if game["won"] else "lost"
        summary = f"Level {puzzle.level}: {result} in {len(game['moves'])} moves; "
        summary += f"the shortest route takes {puzzle.level}"
        examples.append({"title": f"{player}, full context", "summary": summary, "frames": frames})
    return examples


def replay_section(examples: Sequence[dict[str, Any]]) -> str:
    """Recorded games side by side, each stepped through with its own two buttons."""
    if not examples:
        return ""
    data = json.dumps(list(examples)).replace("</", "<\\/")
    boxes = "".join(
        f'<div class="replay" data-game="{i}"><h3>{html.escape(game["title"])}</h3>'
        f'<div class="muted">{html.escape(game["summary"])}</div><pre></pre><p></p>'
        '<div><button aria-label="Previous move">&larr;</button>'
        '<button aria-label="Next move">&rarr;</button></div></div>'
        for i, game in enumerate(examples)
    )
    return f"""<h2>Watch two recorded games</h2>
<p>Follow two games one move at a time to see how the players behave: where they make
progress, take a detour or repeat an earlier mistake. An <i>optimal</i> move starts a shortest
route from where the agent is, even if earlier moves already took it off the shortest route from
the start. These are saved benchmark games, so playing them back makes no new model requests.</p>
<p class="key"><b>A</b> agent &middot; <b>G</b> goal &middot; <b>K</b> key &middot;
<b>D</b> locked door &middot; <b>#</b> wall</p>
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


KIND_NAMES = {"decision": "decision model", "chat": "chat model", "baseline": "baseline"}


def board_row(entry: dict[str, Any]) -> str:
    """A leaderboard row: the player and its details, then games won and progress per condition."""
    name = html.escape(entry["name"])
    link = page_url(entry["url"])
    player = f'<a href="{html.escape(link)}">{name}</a>' if link else name
    cells = [
        f'<td class="player">{player}<div class="muted">{KIND_NAMES[entry["kind"]]}</div>'
        f"<details><summary>details</summary>{html.escape(entry['notes'])}</details></td>"
    ]
    for condition in ("everything", "map"):
        scores = entry["conditions"][condition]
        full = ' class="full"' if condition == "everything" else ""
        won, progress = scores["won"], scores["progress"]
        cells.append(
            f"<td{full}>{won[0] * 100:.0f} / 100"
            f'<span class="ci"> [{won[1] * 100:.0f}&ndash;{won[2] * 100:.0f}]</span></td>'
        )
        cells.append(
            f"<td{full}>{progress[0]:.2f}"
            f'<span class="ci"> [{progress[1]:.2f}&ndash;{progress[2]:.2f}]</span></td>'
        )
    cost = entry["cost"]
    cells.append(f"<td>{'&mdash;' if cost is None else dollars(cost, entry['kind'])}</td>")
    return "<tr>" + "".join(cells) + "</tr>"


def build_page(entries: Sequence[dict[str, Any]], examples: Sequence[dict[str, Any]] = ()) -> str:
    """The leaderboard as one static page: the question, two replays, the table and the setup."""
    models = [board_row(e) for e in ranked(entries) if e["kind"] != "baseline"]
    baselines = [board_row(e) for e in ranked(entries) if e["kind"] == "baseline"]
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>System-One Control Bench</title>
<style>
:root {{ --bg: #fbfbfa; --fg: #1d1d1b; --muted: #5f5f5a; --line: #e2e1db; --head: #f0efea;
  --full: #eef3fb; --link: #1f5fbf; color-scheme: light; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg: #171716; --fg: #ececea; --muted: #a3a39d; --line: #2e2e2a; --head: #22221f;
    --full: #1c2330; --link: #8ab4f8; color-scheme: dark; }}
}}
body {{ background: var(--bg); color: var(--fg); margin: 0;
  font: 16px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }}
main {{ max-width: 1000px; margin: 0 auto; padding: 32px 16px 48px; }}
h1 {{ font-size: 1.9rem; margin: 0 0 4px; text-align: center; }}
.question {{ text-align: center; font-size: 1.15rem; margin: 0 0 20px; }}
h2 {{ font-size: 1.3rem; margin: 40px 0 8px; }}
h3 {{ font-size: 1rem; margin: 0; }}
a {{ color: var(--link); }}
.muted {{ color: var(--muted); font-size: 0.88rem; }}
.links {{ text-align: center; font-size: 1.05rem; }}
.links a {{ margin: 0 10px; }}
.key {{ text-align: center; }}
.scroll {{ overflow-x: auto; margin: 16px 0; }}
table {{ border-collapse: collapse; font-size: 0.95rem; }}
th, td {{ padding: 8px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }}
th {{ background: var(--head); white-space: nowrap; }}
.board {{ width: 100%; }}
.board th, .board td {{ text-align: right; font-variant-numeric: tabular-nums; }}
.board th:first-child, .board td.player {{ text-align: left; }}
.board th[colspan] {{ text-align: center; }}
.board .full {{ background: var(--full); }}
.board .group td {{ text-align: left; font-weight: 600; background: var(--head); }}
.board .ci {{ display: none; color: var(--muted); font-size: 0.85rem; }}
.board.intervals .ci {{ display: inline; }}
.player summary {{ color: var(--muted); font-size: 0.85rem; cursor: pointer; }}
.player details {{ color: var(--muted); font-size: 0.85rem; max-width: 320px; }}
.info th, .info td {{ text-align: left; }}
.replays {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 24px 56px; }}
.replay {{ display: flex; flex-direction: column; align-items: center; min-width: 280px; }}
.replay pre {{ text-align: left; font-size: 1.3rem; line-height: 1.2; padding: 12px 18px;
  border: 1px solid var(--line); border-radius: 6px; margin: 10px 0 auto; }}
.replay button {{ font-size: 1.2rem; padding: 4px 18px; margin: 0 6px; cursor: pointer; }}
</style>
</head>
<body>
<main>
<h1>System-One Control Bench</h1>
<p class="question"><b>How well do individual decisions add up to a completed task?</b></p>
<p>Some AI models write an answer. Others choose from a list of possible answers. This project
tests whether such decision models can guide an agent through a small grid puzzle, and how they
compare with chat models and simple programmed strategies.</p>
<p>The task is easy to describe: reach the goal, avoid walls, and collect a key when a locked door
blocks the way. At each move, the model sees the puzzle as text and chooses its next move from a
list. It then sees the new situation and chooses again, so to finish it has to keep making useful
decisions over many moves. Because the puzzles are small, a solver knows the shortest route from
every position. That lets us check both whether a model finishes a puzzle and whether each move
was one of the best available; often several moves are equally good.</p>
<p><b>Does explaining the situation help?</b> Every model receives the complete map, the rules,
its position and whether it carries the key. We also test what happens when code explains parts
of the situation for it: what is nearby, which moves it has already made, what each possible move
would do, and which object to aim for next. These additions help separate two challenges:
reading the map and choosing what to do.</p>
<p><b>What did we find?</b> More detailed descriptions often help, but strong single decisions do
not guarantee a finished game. With full context, Jev chooses an optimal move in about 90% of the
positions of a separate exam, where every model answers the same fixed situations, yet it
finishes only 57 of the 100 puzzles when it plays whole games. One test measures decisions in
shared situations; the other measures whether a model can carry a task through to the end.</p>
<p>The puzzles, recorded games, code and analysis are public. This is a small, fixed benchmark
for studying sequential decisions; the report explains the methods, results and limits.</p>
<p class="links"><a href="{REPO}/blob/main/paper/main.pdf">Read the report</a> &middot;
<a href="{REPO}">Explore the code and data</a> &middot;
<a href="{REPO}/blob/main/SUBMITTING.md">Submit a model</a></p>
{replay_section(examples)}
<h2>Leaderboard</h2>
<p>Each player attempts the same 100 puzzles, one step per move, under two conditions:</p>
<ul>
<li><b>Map only:</b> the rules, the complete map, the agent's position and whether it carries
the key.</li>
<li><b>Full context:</b> everything in map only, plus the surroundings, the move history, the
outcome of each move on offer and the next target.</li>
</ul>
<p>Players are sorted by full-context games won. <b>Games won</b> counts the puzzles finished
within the move limit, which is twice the shortest route. <b>Mean progress</b> measures how much
closer the agent got to the goal at its best point in each game, averaged over the 100 puzzles: 1
means finished, 0 means it never got closer than where it started. <b>Reported API cost</b>
covers both conditions together, 200 games; a dash means no cost was reported, and local
computing is not included. The baselines are reference points: random moves, two greedy
strategies and a solver that always chooses an optimal move.</p>
<p><label><input type="checkbox"
 onchange="document.getElementById('board').classList.toggle('intervals', this.checked)">
Show 95% intervals (how much each score depends on which puzzles are in the set)</label></p>
<div class="scroll">
<table class="board" id="board"><thead>
<tr><th rowspan="2">Player</th><th colspan="2" class="full">Full context</th>
<th colspan="2">Map only</th><th rowspan="2">Reported API<br>cost (USD)</th></tr>
<tr><th class="full">Games won</th><th class="full">Mean progress</th>
<th>Games won</th><th>Mean progress</th></tr>
</thead><tbody>
{"".join(models)}
<tr class="group"><td colspan="6">Programmed baselines (they do not read the request)</td></tr>
{"".join(baselines)}
</tbody></table>
</div>
<p class="muted">The <a href="{REPO}/blob/main/leaderboard/README.md">full table</a> adds SPL
and the time per answer.</p>
<h2>What information does a player receive?</h2>
<p>The complete map is always available. Four optional components explain the situation in
different ways:</p>
<div class="scroll"><table class="info"><thead><tr><th>Component</th>
<th>What it tells the player</th></tr></thead><tbody>
{COMPONENT_ROWS}
</tbody></table></div>
<p>These descriptions are produced by code. They are real help, so the results measure the
model together with the information it receives. The study tests ten conditions: the map alone,
each component on its own, all four together (full context), and all four with one removed.
This shows both whether a component helps by itself and whether it still matters when the others
are present.</p>
<details><summary>All ten conditions</summary>
<div class="scroll"><table class="info"><thead><tr><th>Condition</th><th>Name in the code</th>
<th>Added to the map</th></tr></thead><tbody>
{CONDITION_ROWS}
</tbody></table></div></details>
<h2>Choosing several steps at once</h2>
<p>The leaderboard uses one step per move, with four directions on offer. The wider study also
tests moves of two or three steps chosen together, including rules where shorter moves stay
available. Under these rules the player commits to a whole sequence before seeing the new
situation: a blocked step is wasted, but the remaining steps still run, and reaching the goal
ends the move. Longer moves change both the number of options and how far the agent goes before
the player sees the board again.</p>
<div class="scroll"><table class="info"><thead><tr><th>Rules</th><th>One move is</th>
<th>Options</th></tr></thead><tbody>
{RULE_ROWS}
</tbody></table></div>
</main>
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
        "# Leaderboard\n\nCore track, sorted by full-context games won, best first.\n\n"
        + LEGEND
        + "\n"
        + build_table(entries),
        encoding="utf-8",
        newline="",
    )
    page = (docs or leaderboard.parents[0] / "docs") / "index.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(build_page(entries, example_games(leaderboard)), encoding="utf-8", newline="")
    return readme, page

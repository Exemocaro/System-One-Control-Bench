import json

import httpx
import pytest
from typer.testing import CliRunner

from system_one_control.bench import (
    BENCHMARK_VERSION,
    fingerprint,
    run_benchmark,
    save,
    validate_file,
)
from system_one_control.cli import app
from system_one_control.leaderboard import (
    build_page,
    dollars,
    player_cell,
    rebuild,
    safe,
    shown,
    submit,
)
from system_one_control.players import PlayerEntry, players_from_toml
from system_one_control.players.baselines import SolverPlayer
from system_one_control.players.remote import DecisionPlayer, LLMPlayer
from system_one_control.prompts import CONDITIONS
from system_one_control.puzzles import load_puzzles
from tests.helpers import MAP, turn

runner = CliRunner()
EVERYTHING = CONDITIONS["everything"]


def test_track_core_plays_compass_map_and_everything(tmp_path):
    out = tmp_path / "core.jsonl"
    result = runner.invoke(
        app,
        ["benchmark", "--track", "core", "--players", "solver", "--levels", "1", "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    games = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert {(g["condition"], g["rules"]) for g in games} == {
        ("map", "compass"),
        ("everything", "compass"),
    }
    assert {g["puzzle"] for g in games} == {f"gen-01-0{n}" for n in range(1, 6)}


def test_a_track_cannot_be_combined_with_conditions_or_rules(tmp_path):
    out = tmp_path / "r.jsonl"
    result = runner.invoke(app, ["benchmark", "--track", "core", "--conditions", "map"])
    assert result.exit_code != 0
    assert "cannot be combined" in result.output
    assert not out.exists()


def test_an_unknown_track_is_refused():
    result = runner.invoke(app, ["benchmark", "--track", "extended"])
    assert result.exit_code != 0
    assert "unknown track" in result.output


TOML = """
[players.chatty]
kind = "chat"
base_url = "https://api.example.com/v1"
model = "my-model-1"
api_key_env = "MY_API_KEY"
reasoning = false

[players.brain]
kind = "decision"
url = "https://api.example.com/decide"
api_key_env = "MY_API_KEY"
"""


def test_players_from_toml_builds_chat_and_decision_players(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_API_KEY", "secret")
    path = tmp_path / "players.toml"
    path.write_text(TOML, encoding="utf-8")
    entries = players_from_toml(path)
    assert set(entries) == {"chatty", "brain"}
    assert all(isinstance(entry, PlayerEntry) for entry in entries.values())
    assert entries["chatty"].paid and entries["brain"].paid


def test_chat_is_paid_unless_the_file_says_otherwise(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_API_KEY", "secret")
    path = tmp_path / "players.toml"
    free = '\n[players.free]\nkind = "chat"\nbase_url = "https://x/v"\nmodel = "m"\npaid = false\n'
    path.write_text(TOML + free, encoding="utf-8")
    assert not players_from_toml(path)["free"].paid


@pytest.mark.parametrize(
    ("section", "message"),
    [
        ('[players.random]\nkind = "chat"\nbase_url = "https://x/v"\nmodel = "m"', "clashes"),
        ('[players.x]\nkind = "carrier-pigeon"', "kind must be chat or decision"),
        ('[players.x]\nkind = "chat"\nmodel = "m"', "needs 'base_url'"),
        ('[players.x]\nkind = "decision"', "needs 'url'"),
        (
            '[players.x]\nkind = "chat"\nbase_url = "https://x/v"\nmodel = "m"\n'
            'api_key_env = "NO_SUCH_KEY_XYZ"',
            "NO_SUCH_KEY_XYZ",
        ),
    ],
    ids=[
        "a name clash with a built-in",
        "an unknown kind",
        "a chat player without a url",
        "a decision player without a url",
        "a missing api key variable",
    ],
)
def test_bad_toml_entries_are_refused(tmp_path, section, message):
    path = tmp_path / "players.toml"
    path.write_text(section + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        players_from_toml(path)


def test_fingerprint_is_stable_and_versioned():
    assert fingerprint() == fingerprint()
    assert len(fingerprint()) == 64
    assert BENCHMARK_VERSION == "1.0"


def tiny_run():
    puzzles = list(load_puzzles().values())[:2]
    return run_benchmark(puzzles, [MAP, EVERYTHING], {"solver": SolverPlayer})


def tiny_names():
    return {puzzle.name for puzzle in list(load_puzzles().values())[:2]}


def scope(monkeypatch, names):
    """Check coverage against these puzzles instead of all 100."""
    puzzles = load_puzzles()
    first = next(iter(puzzles.values()))
    monkeypatch.setattr(
        "system_one_control.leaderboard.load_puzzles",
        lambda: {name: puzzles.get(name, first) for name in names},
    )


def tiny_file(tmp_path):
    return save(tiny_run(), tmp_path / "tiny.jsonl")


def test_validate_passes_a_real_small_run(tmp_path):
    assert validate_file(tiny_file(tmp_path)) == []


def peak_elsewhere(game):
    """Move 0.97 of the probability onto another option than the move."""
    first = game["moves"][0]
    other = next(option for option in first["options"] if option != first["move"])
    first["probabilities"] = {other: 0.97, first["move"]: 0.01}


@pytest.mark.parametrize(
    "tamper",
    [
        pytest.param(
            lambda game: game["moves"][0].__setitem__("move", "jump"),
            id="an answer outside the options",
        ),
        pytest.param(
            lambda game: game["moves"].__setitem__(
                0, {**game["moves"][0], "options": ["west", "east", "north", "south"]}
            ),
            id="options in another order",
        ),
        pytest.param(lambda game: game.__setitem__("won", not game["won"]), id="a flipped outcome"),
        pytest.param(peak_elsewhere, id="a probability peak on another move"),
        pytest.param(
            lambda game: game.__setitem__("level", game["level"] * 50), id="a raised level"
        ),
        pytest.param(
            lambda game: game.__setitem__("condition", "map+all"), id="an unknown condition"
        ),
        pytest.param(lambda game: game["moves"].pop(), id="a game cut short"),
    ],
)
def test_validate_fails_a_tampered_game(tmp_path, tamper):
    path = tiny_file(tmp_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    game = json.loads(lines[0])
    tamper(game)
    lines[0] = json.dumps(game)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert validate_file(path) != []


def test_submit_writes_an_entry_and_core_games_then_rebuilds_the_table(tmp_path, monkeypatch):
    scope(monkeypatch, tiny_names())
    path = tiny_file(tmp_path)
    board = tmp_path / "board"
    entry = submit(
        [path],
        name="Tiny Solver",
        org="",
        url="",
        notes="",
        leaderboard=board,
    )
    saved = json.loads(entry.read_text(encoding="utf-8"))
    assert saved["player"] == "solver" and saved["track"] == "core"
    assert saved["results"] == "solver.jsonl"
    assert set(saved["conditions"]) == {"map", "everything"}
    assert saved["conditions"]["map"]["progress"][0] == 1.0
    assert len((board / "results" / "solver.jsonl").read_text(encoding="utf-8").splitlines()) == 4
    readme, page = rebuild(leaderboard=board, docs=tmp_path / "docs")
    assert "Tiny Solver" in readme.read_text(encoding="utf-8")
    assert "Tiny Solver" in page.read_text(encoding="utf-8")


def rewrite(path, tamper):
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(tamper(lines)) + "\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        pytest.param(lambda lines: lines + lines[:1], "duplicate games", id="a duplicated game"),
        pytest.param(
            lambda lines: [
                json.dumps(json.loads(lines[0]) | {"rules": "two-moves"}),
                *lines[1:],
            ],
            "only compass",
            id="a non-compass game",
        ),
    ],
)
def test_submit_refuses_games_outside_the_core_track(tmp_path, tamper, message, monkeypatch):
    scope(monkeypatch, tiny_names())
    path = tiny_file(tmp_path)
    rewrite(path, tamper)
    with pytest.raises(ValueError, match=message):
        submit(
            [path],
            name="x",
            org="",
            url="",
            notes="",
            leaderboard=tmp_path / "b",
        )


def test_submit_needs_a_kind_for_players_outside_the_baselines(tmp_path, monkeypatch):
    scope(monkeypatch, tiny_names())
    path = tiny_file(tmp_path)
    rewrite(
        path,
        lambda lines: [json.dumps(json.loads(line) | {"player": "fakegpt"}) for line in lines],
    )
    args = {
        "name": "x",
        "org": "",
        "url": "",
        "notes": "",
        "leaderboard": tmp_path / "b",
    }
    with pytest.raises(ValueError, match="--kind"):
        submit([path], **args)
    entry = submit([path], kind="chat", **args)
    assert json.loads(entry.read_text(encoding="utf-8"))["kind"] == "chat"


@pytest.mark.parametrize(
    ("text", "expected"),
    [("a|b", "a/b"), ("a\nb", "a b"), ("plain", "plain")],
    ids=["pipes become slashes", "newlines become spaces", "plain text stays"],
)
def test_names_are_safe_for_the_markdown_table(text, expected):
    assert safe(text) == expected


def hostile_entry():
    stats = {"won": [0.5, 0.4, 0.6], "progress": [0.5, 0.4, 0.6], "spl": [0.5, 0.4, 0.6]}
    return {
        "name": "x</script><img src=x onerror=y>",
        "player": "x",
        "org": "",
        "url": "javascript:alert(1)",
        "notes": "",
        "kind": "chat",
        "benchmark": "1.0+abc",
        "track": "core",
        "results": "x.jsonl",
        "conditions": {"map": stats, "everything": stats},
        "cost": 0.1,
        "latency": 0.5,
        "date": "2026-10-03",
    }


def test_the_page_escapes_names_and_links():
    page = build_page([hostile_entry()])
    assert "</script><img" not in page and "javascript:" not in page
    assert "&lt;/script&gt;" in page


def test_submit_refuses_a_run_with_missing_or_mixed_players(tmp_path, monkeypatch):
    path = tiny_file(tmp_path)
    names = tiny_names()
    scope(monkeypatch, names | {"nope"})
    with pytest.raises(ValueError, match="missing game"):
        submit([path], name="x", org="", url="", notes="", leaderboard=tmp_path / "b")
    scope(monkeypatch, names)
    lines = path.read_text(encoding="utf-8").splitlines()
    game = json.loads(lines[0])
    game["player"] = "impostor"
    lines[0] = json.dumps(game)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="one player"):
        submit([path], name="x", org="", url="", notes="", leaderboard=tmp_path / "b")


def test_a_given_client_skips_the_api_key_lookup(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client, _ = watching({"choices": [{"message": {"content": '{"option": "option_1"}'}}]})
    player = LLMPlayer("m", reasoning=False, client=client)
    assert player.choose(turn("####\n#AG#\n####")).move is not None


def watching(reply) -> tuple[httpx.Client, list[dict]]:
    """A client that records what it is sent and answers one reply."""
    sent: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=reply)

    return httpx.Client(transport=httpx.MockTransport(handle)), sent


@pytest.mark.parametrize(
    ("player", "kind", "message"),
    [
        ("fakegpt", "baseline", "only random, greedy, greedy-walls, solver are baselines"),
        ("Bad Name!", None, "a-z0-9"),
    ],
    ids=["baseline kind for another player", "a player name outside [a-z0-9._-]"],
)
def test_submit_names_are_checked(tmp_path, monkeypatch, player, kind, message):
    scope(monkeypatch, tiny_names())
    path = tiny_file(tmp_path)
    rewrite(
        path,
        lambda lines: [json.dumps(json.loads(line) | {"player": player}) for line in lines],
    )
    with pytest.raises(ValueError, match=message):
        submit(
            [path],
            name="x",
            org="",
            url="",
            notes="",
            kind=kind,
            leaderboard=tmp_path / "b",
        )


@pytest.mark.parametrize(
    ("name", "url", "expected"),
    [
        ("m", "https://example.com/m", "[m](https://example.com/m)"),
        ("m", "javascript:alert(1)", "m"),
        ("m", "https://example.com/a)b", "m"),
        ("a|b</>", "https://example.com", "[a/b&lt;/&gt;](https://example.com)"),
    ],
    ids=["a clean link", "no javascript links", "no brackets in links", "escaped text"],
)
def test_the_table_links_names_safely(name, url, expected):
    assert player_cell({"name": name, "url": url}) == expected


def test_rebuild_refuses_an_entry_named_for_another_player(tmp_path, monkeypatch):
    scope(monkeypatch, tiny_names())
    path = tiny_file(tmp_path)
    board = tmp_path / "board"
    submit([path], name="Tiny Solver", org="", url="", notes="", leaderboard=board)
    entry = board / "entries" / "solver.json"
    (board / "entries" / "x.json").write_text(entry.read_text(encoding="utf-8"), encoding="utf-8")
    entry.unlink()
    with pytest.raises(ValueError, match=r"x[.]json"):
        rebuild(leaderboard=board, docs=tmp_path / "docs")


def test_a_chat_model_elsewhere_gets_no_openrouter_fields():
    request = turn("####\n#AG#\n####").request
    client, sent = watching({"choices": [{"message": {"content": '{"option": "option_1"}'}}]})
    player = LLMPlayer("m", reasoning=True, base_url="https://api.example.com/v1", client=client)
    assert player.choose(turn("####\n#AG#\n####")).move == request.options[0].move
    assert "provider" not in sent[0] and "usage" not in sent[0] and "reasoning" not in sent[0]
    assert sent[0]["model"] == "m"


@pytest.mark.parametrize(
    ("reply", "move", "error"),
    [
        ({"probabilities": {"option_2": 0.7, "option_1": 0.2}}, "south", None),
        ({"choice": "option_4"}, "west", None),
        ({"choice": "option_9"}, None, "option_9"),
        ({"something": "else"}, None, "neither"),
    ],
    ids=[
        "the likeliest probability wins",
        "a bare choice is played",
        "an unknown id is an error",
        "neither is an error",
    ],
)
def test_a_decision_endpoint_answers_probabilities_or_a_choice(reply, move, error):
    t = turn("####\n#AG#\n####")
    client, sent = watching(reply)
    player = DecisionPlayer("https://api.example.com/decide", client=client, retry_waits=(0, 0))
    choice = player.choose(t)
    expected = next((o.move for o in t.request.options if o.move == move), None)
    assert choice.move == expected
    assert (choice.error is None) == (error is None)
    if error:
        assert error in choice.error
    assert sent[0]["options"] == [{"id": o.id, "text": o.text} for o in t.request.options]


def test_unreported_cost_is_na_and_free_is_zero():
    assert shown(None, "chat") == "n/a"
    assert shown(None, "baseline") == "0"
    assert shown(0.0, "decision") == "0"
    assert shown(0.7121, "chat") == "0.7121"


def test_page_costs_round_up_to_the_cent():
    assert dollars(0.7121, "chat") == "0.72"
    assert dollars(0.0954, "chat") == "0.10"
    assert dollars(0.07, "chat") == "0.07"
    assert dollars(None, "chat") == "n/a"
    assert dollars(None, "baseline") == "0"

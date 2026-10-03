import json
import threading
from dataclasses import replace

import pytest

from system_one_control.bench import (
    Game,
    GameRecord,
    MoveRecord,
    check_same_run,
    estimate_paid_calls,
    load,
    run_benchmark,
    save,
    scores,
    split_finished,
    summarize,
    usage,
)
from system_one_control.players import Choice, Player, Turn
from system_one_control.players.baselines import (
    RandomPlayer,
    ScriptedPlayer,
    SolverPlayer,
    WallAwareGreedyPlayer,
)
from system_one_control.prompts import CONDITIONS
from system_one_control.puzzles import load_puzzles
from system_one_control.world import ThreeMoveRules, TwoMoveRules
from tests.helpers import MAP, AlwaysPlayer, puzzle

PUZZLES = load_puzzles()
ALL = list(CONDITIONS.values())
ONLY_MAP = [MAP]
CORRIDOR = "#######\n#A...G#\n#######"
SHORT = "#####\n#A.G#\n#####"
ONE_MOVE = "####\n#AG#\n####"


class FailingPlayer(Player):
    def choose(self, turn: Turn) -> Choice:
        raise ConnectionError("the API is down")


def move(**fields) -> MoveRecord:
    return MoveRecord(("east",), "east", {}, ("east",), True, **fields)


def record(player="jev", moves=(), key=("s", "map"), error=None) -> GameRecord:
    return GameRecord(key[0], key[1], player, 1, error is None, 0, error, tuple(moves))


def solved(puzzles, **more):
    return run_benchmark(puzzles, ONLY_MAP, {"solver": SolverPlayer}, **more)


def untimed(records):
    """The records without how long each move took, which no two runs share."""
    return [replace(r, moves=tuple(replace(m, seconds=None) for m in r.moves)) for r in records]


# The game


@pytest.mark.parametrize("name", PUZZLES)
def test_the_solver_wins_every_puzzle_in_the_fewest_moves(name):
    game = Game(PUZZLES[name], SolverPlayer(), MAP)
    steps = game.play()
    assert (game.won, len(steps), all(s.optimal for s in steps)) == (
        True,
        PUZZLES[name].level,
        True,
    )


@pytest.mark.parametrize(
    ("text", "level", "player", "moves", "error"),
    [
        (SHORT, 2, AlwaysPlayer("west"), 4, None),
        (ONE_MOVE, 1, AlwaysPlayer("jump"), 1, "'jump' is not an allowed move"),
        (SHORT, 2, FailingPlayer(), 1, "ConnectionError: the API is down"),
    ],
    ids=[
        "twice the fewest moves is the limit",
        "an answer that is not a move",
        "a player that raises",
    ],
)
def test_a_game_that_ends_without_a_win(text, level, player, moves, error):
    game = Game(puzzle(text, level), player, MAP)
    steps = game.play()
    assert (len(steps), game.is_over, game.won, steps[-1].choice.error) == (
        moves,
        True,
        False,
        error,
    )


def test_a_step_records_the_board_before_and_after_and_whether_it_was_best():
    step = Game(puzzle(SHORT, 2), AlwaysPlayer("west"), MAP).step()
    assert (step.number, step.before == step.after, step.best_moves, step.optimal) == (
        1,
        True,
        ("east",),
        False,
    )
    assert "#A.G#" in step.request.state


def test_no_move_can_be_played_after_the_game_is_over():
    game = Game(puzzle(ONE_MOVE, 1), SolverPlayer(), MAP)
    game.play()
    with pytest.raises(RuntimeError, match="over"):
        game.step()


@pytest.mark.parametrize(
    ("player", "condition", "steps", "fragment"),
    [
        (SolverPlayer(), MAP, 1, "#.AG#"),
        (
            AlwaysPlayer("west"),
            CONDITIONS["map+memory"],
            2,
            "1. west: blocked, you stay at (1, 1)\n2. west: blocked, you stay at (1, 1)",
        ),
    ],
    ids=["the board after a move", "the memory of every move"],
)
def test_the_next_request_shows_what_has_happened(player, condition, steps, fragment):
    game = Game(puzzle(SHORT, 2), player, condition)
    for _ in range(steps):
        game.step()
    assert fragment in game.next_request().state


def test_the_previewed_request_is_exactly_what_the_player_is_then_asked():
    game = Game(puzzle(SHORT, 2), SolverPlayer(), MAP)
    preview = game.next_request()
    assert game.step().request == preview


def test_each_move_is_asked_with_its_own_option_order():
    game = Game(puzzle("########\n#A....G#\n########", 5), SolverPlayer(), MAP)
    assert len({tuple(o.move for o in s.request.options) for s in game.play()}) > 1


def test_a_game_asked_to_stop_stops_between_moves():
    game = Game(puzzle("########\n#A....G#\n########", 5), SolverPlayer(), MAP)
    stop = threading.Event()
    game.step()
    stop.set()
    assert (len(game.play(stop)), game.is_over) == (1, False)


def test_under_sequence_rules_the_solver_wins_in_the_fewest_sequences():
    played = replace(PUZZLES["gen-10-01"], rules=ThreeMoveRules())
    game = Game(played, SolverPlayer(), MAP)
    steps = game.play()
    assert (game.won, len(steps), all(s.optimal for s in steps)) == (True, 4, True)
    assert "," in steps[0].choice.move


@pytest.mark.parametrize("answer", ["east,north", "east,west"], ids=["a step nearer", "back again"])
def test_under_sequence_rules_the_closest_distance_counts_compass_moves_along_the_way(answer):
    game = Game(replace(puzzle(CORRIDOR, 4), rules=TwoMoveRules()), AlwaysPlayer(answer), MAP)
    game.step()
    assert game.closest == 3  # one compass move nearer, though no sequence was saved


@pytest.mark.parametrize("rules", [TwoMoveRules(), ThreeMoveRules()], ids=lambda r: r.name)
def test_the_best_moves_worked_out_once_agree_with_a_fresh_search_at_every_move(rules):
    played = replace(PUZZLES["gen-10-01"], rules=rules)
    game = Game(played, AlwaysPlayer("east," * (rules.length - 1) + "south"), MAP)
    assert all(s.best_moves == game.solver.best_moves(s.before) for s in game.play())


# The scores


@pytest.mark.parametrize(
    ("text", "level", "answers", "expected"),
    [
        (CORRIDOR, 4, ["east"] * 4, (1, 1.0, 1.0, 0)),
        (CORRIDOR, 4, ["east", "east", "west"], (0, 0.5, 0.0, 1)),
        (CORRIDOR, 4, ["west"] * 8, (0, 0.0, 0.0, 0)),
        ("######\n#.A.G#\n######", 2, ["west", "east", "east", "east"], (1, 1.0, 0.5, 0)),
        (ONE_MOVE, 1, ["jump"], (0, 0.0, 0.0, 1)),
    ],
    ids=[
        "a win in the fewest moves",
        "closest was halfway, then it ran out of answers",
        "a lost game",
        "a slow win scores less than one",
        "an answer that is no move is an error",
    ],
)
def test_a_game_is_scored_by_won_progress_spl_and_errors(text, level, answers, expected):
    records = run_benchmark([puzzle(text, level)], ONLY_MAP, {"p": lambda: ScriptedPlayer(answers)})
    score = scores(records)[("p", "map")]
    assert (score.won, score.progress, score.spl, score.errors) == expected


def test_the_summary_counts_games_won_at_each_level_and_then_the_scores():
    games = len(PUZZLES)
    table = summarize(solved(PUZZLES.values())).splitlines()
    assert table[0].split()[:4] == ["player", "condition", "1", "away"]
    assert table[0].split()[-4:] == ["won", "progress", "SPL", "errors"]
    assert table[2].split()[-4:] == [f"{games}/{games}", "1.00", "1.00", "0"]


def test_rows_run_from_random_to_the_solver_with_other_players_below():
    records = run_benchmark(
        list(PUZZLES.values())[:3],
        ONLY_MAP,
        {"always": lambda: AlwaysPlayer("west"), "solver": SolverPlayer, "random": RandomPlayer},
    )
    assert [line.split()[0] for line in summarize(records).splitlines()[2:]] == [
        "random",
        "solver",
        "always",
    ]


def test_the_best_number_in_each_column_is_bold_leaving_out_the_solver():
    records = run_benchmark(
        PUZZLES.values(), ONLY_MAP, {"random": RandomPlayer, "solver": SolverPlayer}
    )
    random_row, solver_row = summarize(records, bold_best=True).splitlines()[2:]
    assert ("\x1b[1m" in random_row, "\x1b[1m" in solver_row, "\x1b[" in summarize(records)) == (
        True,
        False,
        False,
    )


def test_the_columns_line_up():
    records = run_benchmark(
        PUZZLES.values(), ONLY_MAP, {"random": RandomPlayer, "greedy-walls": WallAwareGreedyPlayer}
    )
    assert len({len(line) for line in summarize(records).splitlines()}) == 1


@pytest.mark.parametrize(
    ("player", "moves", "expected"),
    [
        ("jev", [move(input_tokens=100)] * 2, "jev: 2 calls, 200 input tokens, 0 output tokens"),
        ("random", [move(input_tokens=100)], ""),
        (
            "jev",
            [move(input_tokens=100, output_tokens=2, seconds=s) for s in (0.5, 0.5, 3.0)],
            "jev: 3 calls, 300 input tokens, 6 output tokens, 0.50 s per call (median)",
        ),
        (
            "jev",
            [move(input_tokens=100, retried=("busy", "busy"))],
            "jev: 1 call, 100 input tokens, 0 output tokens, 2 turned away and retried",
        ),
    ],
    ids=["calls and tokens", "a free player is left out", "the median wait", "moves turned away"],
)
def test_usage_counts_the_calls_and_tokens_of_paid_players_only(player, moves, expected):
    assert usage([record(player, moves)]) == expected


@pytest.mark.parametrize(
    ("conditions", "players", "done", "expected"),
    [
        (ALL, ["jev", "random"], set(), sum(p.max_moves for p in PUZZLES.values()) * len(ALL)),
        (ALL, ["random"], set(), 0),
        (
            ONLY_MAP,
            ["jev"],
            {("gen-01-01", "map", "jev")},
            sum(p.max_moves for p in PUZZLES.values()) - PUZZLES["gen-01-01"].max_moves,
        ),
    ],
    ids=[
        "every move of a paid player",
        "none for a free player",
        "games already done are left out",
    ],
)
def test_paid_calls_are_estimated_before_anything_runs(conditions, players, done, expected):
    assert estimate_paid_calls(list(PUZZLES.values()), conditions, players, done=done) == expected


# Playing, saving and loading


def test_there_is_one_record_per_puzzle_condition_and_player():
    records = run_benchmark(
        list(PUZZLES.values())[:2], ALL, {"solver": SolverPlayer, "random": RandomPlayer}
    )
    assert len(records) == 2 * len(ALL) * 2
    assert {r.condition for r in records} == set(CONDITIONS)


def test_a_game_records_its_rules_and_spl_counts_their_moves():
    played = replace(puzzle(CORRIDOR, 4), rules=TwoMoveRules())
    [saved] = run_benchmark([played], ONLY_MAP, {"solver": SolverPlayer})
    assert (saved.rules, saved.won, len(saved.moves), saved.fewest_moves) == (
        "two-moves",
        True,
        2,
        2,
    )


def test_games_played_side_by_side_give_the_same_records_in_the_same_order():
    players = {"random": RandomPlayer, "solver": SolverPlayer}
    one_at_a_time = run_benchmark(PUZZLES.values(), ONLY_MAP, players)
    side_by_side = run_benchmark(PUZZLES.values(), ONLY_MAP, players, workers=8)
    assert untimed(side_by_side) == untimed(one_at_a_time)


def test_each_game_is_handed_over_as_soon_as_it_finishes():
    handed: list[GameRecord] = []
    records = solved(list(PUZZLES.values())[:5], workers=4, on_record=handed.append)
    assert sorted(handed, key=records.index) == records


def test_games_already_done_are_skipped():
    first, second = list(PUZZLES.values())[:2]
    records = solved([first, second], done={(first.name, "map", "solver")})
    assert [r.puzzle for r in records] == [second.name]


def test_a_failure_outside_a_move_stops_the_run_and_keeps_the_games_already_handed_over():
    handed: list[GameRecord] = []
    built = 0

    def build() -> Player:
        nonlocal built
        built += 1
        if built == 3:
            raise RuntimeError("could not start a player")
        return SolverPlayer()

    with pytest.raises(RuntimeError, match="could not start"):
        run_benchmark(PUZZLES.values(), ONLY_MAP, {"solver": build}, on_record=handed.append)
    assert (len(handed), built) == (2, 3)  # the games after it were never started


def test_every_player_is_closed_after_its_game():
    closed = []

    class ClosingPlayer(SolverPlayer):
        def close(self) -> None:
            closed.append(self)

    run_benchmark(list(PUZZLES.values())[:3], ONLY_MAP, {"ClosingPlayer": ClosingPlayer}, workers=2)
    assert len(closed) == 3


def test_a_record_is_saved_as_one_json_line_with_every_move():
    [saved] = solved(list(PUZZLES.values())[:1])
    line = json.loads(saved.to_json())
    first = line["moves"][0]
    assert (line["player"], line["condition"]) == ("solver", "map")
    assert sorted(first["options"]) == ["east", "north", "south", "west"]
    assert first["move"] in first["best_moves"] and first["optimal"]
    assert first["probabilities"] == {first["move"]: 1.0}
    assert first["seconds"] >= 0


def test_saved_games_load_back_unchanged_and_a_cut_off_last_line_is_skipped(tmp_path):
    records = solved(list(PUZZLES.values())[:3])
    path = save(records, tmp_path / "out.jsonl")
    assert load(path) == records
    with path.open("a", encoding="utf-8") as file:
        file.write('{"puzzle": "half a li')
    assert load(path) == records


def test_a_corrupt_line_before_the_last_is_an_error(tmp_path):
    path = save(solved(list(PUZZLES.values())[:2]), tmp_path / "out.jsonl")
    first, second = path.read_text(encoding="utf-8").splitlines()
    path.write_text(f"{first[:20]}\n{second}\n", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load(path)


def test_a_record_with_moves_turned_away_loads_back_unchanged():
    retried = record(moves=[move(input_tokens=100, retried=("busy", "busy"))])
    assert GameRecord.from_json(retried.to_json()) == retried


@pytest.mark.parametrize(
    ("removed", "name", "expected"),
    [
        (("output_tokens", "confidence", "model", "seconds"), "seconds", None),
        (("rules",), "rules", "compass"),
    ],
    ids=["before the newer move fields", "before rules were recorded"],
)
def test_games_saved_before_a_field_was_added_still_load(tmp_path, removed, name, expected):
    [saved] = solved(list(PUZZLES.values())[:1])
    line = json.loads(saved.to_json())
    for field in removed:
        line.pop(field, None)
        for each in line["moves"]:
            each.pop(field, None)
    path = tmp_path / "old.jsonl"
    path.write_text(json.dumps(line) + "\n", encoding="utf-8")
    [loaded] = load(path)
    assert (loaded.moves[0].seconds if name == "seconds" else loaded.rules) == expected


# Resuming


def test_games_that_ended_in_an_error_are_played_again():
    kept, again = split_finished([record(), record(error="boom"), record()])
    assert (len(kept), len(again)) == (2, 1)


@pytest.mark.parametrize(
    ("loaded", "rules_of", "expected"),
    [
        ([record()], {"s": "compass"}, None),
        ([record(key=("other", "map"))], {"s": "compass", "other": "compass"}, "would not play"),
        ([replace(record(), rules="two-moves")], {"s": "compass"}, "two-moves rules"),
    ],
    ids=["the same run", "a game this run would not play", "other rules"],
)
def test_a_results_file_can_be_resumed_only_by_the_same_run(loaded, rules_of, expected):
    why = check_same_run(loaded, {("s", "map", "jev")}, rules_of)
    assert (why is None) if expected is None else (expected in why)

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
)
from system_one_control.prompts import CONDITIONS
from system_one_control.puzzles import load_puzzles
from system_one_control.world import ThreeMoveRules, TwoMoveRules
from tests.helpers import MAP, AlwaysPlayer, puzzle

PUZZLES = load_puzzles()
FIRST_FIVE = list(PUZZLES.values())[:5]
ALL = list(CONDITIONS.values())
ONLY_MAP = [MAP]
CORRIDOR = "#######\n#A...G#\n#######"
SHORT = "#####\n#A.G#\n#####"
ONE_MOVE = "####\n#AG#\n####"
MEMORY = "1. west: blocked, you stay at (1, 1)\n2. west: blocked, you stay at (1, 1)"
TWO_STEPS = replace(puzzle(CORRIDOR, 4), rules=TwoMoveRules())


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
    played = game.play()
    assert (game.won, len(played), all(p.optimal for p in played)) == (
        True,
        game.puzzle.level,
        True,
    )


@pytest.mark.parametrize(
    ("text", "level", "player", "moves", "error"),
    [
        pytest.param(SHORT, 2, AlwaysPlayer("west"), 4, None, id="twice the fewest moves"),
        pytest.param(
            ONE_MOVE, 1, AlwaysPlayer("jump"), 1, "'jump' is not an allowed move", id="no move"
        ),
        pytest.param(SHORT, 2, FailingPlayer(), 1, "ConnectionError: the API is down", id="raises"),
    ],
)
def test_a_game_that_ends_without_a_win(text, level, player, moves, error):
    game = Game(puzzle(text, level), player, MAP)
    played = game.play()
    assert (len(played), game.is_over, game.won, played[-1].choice.error) == (
        moves,
        True,
        False,
        error,
    )


def test_a_move_records_the_board_before_and_after_and_whether_it_was_best():
    played = Game(puzzle(SHORT, 2), AlwaysPlayer("west"), MAP).play_move()
    assert (played.number, played.before == played.after) == (1, True)
    assert (played.best_moves, played.optimal) == (("east",), False)


def test_no_move_can_be_played_after_the_game_is_over():
    game = Game(puzzle(ONE_MOVE, 1), SolverPlayer(), MAP)
    game.play()
    with pytest.raises(RuntimeError, match="over"):
        game.play_move()


@pytest.mark.parametrize(
    ("player", "condition", "moves", "fragment"),
    [
        pytest.param(SolverPlayer(), MAP, 1, "#.AG#", id="the board after a move"),
        pytest.param(AlwaysPlayer("west"), CONDITIONS["map+memory"], 2, MEMORY, id="the memory"),
    ],
)
def test_the_next_request_shows_what_has_happened(player, condition, moves, fragment):
    game = Game(puzzle(SHORT, 2), player, condition)
    for _ in range(moves):
        game.play_move()
    assert fragment in game.next_request().state


def test_the_previewed_request_is_exactly_what_the_player_is_then_asked():
    game = Game(puzzle(SHORT, 2), SolverPlayer(), MAP)
    preview = game.next_request()
    assert game.play_move().request == preview


def test_a_game_asked_to_stop_stops_between_moves():
    game = Game(puzzle("########\n#A....G#\n########", 5), SolverPlayer(), MAP)
    stop = threading.Event()
    game.play_move()
    stop.set()
    assert (len(game.play(stop)), game.is_over) == (1, False)


def test_under_sequence_rules_the_solver_wins_in_the_fewest_sequences():
    game = Game(replace(PUZZLES["gen-10-01"], rules=ThreeMoveRules()), SolverPlayer(), MAP)
    played = game.play()
    assert (game.won, len(played), all(p.optimal for p in played)) == (True, 4, True)
    assert "," in played[0].choice.move


def test_under_sequence_rules_the_closest_distance_counts_compass_moves_along_the_way():
    game = Game(TWO_STEPS, AlwaysPlayer("east,west"), MAP)
    game.play_move()
    assert game.closest == 3  # one compass move nearer halfway through, though no sequence saved


def test_the_best_moves_worked_out_once_agree_with_a_fresh_search_at_every_move():
    game = Game(
        replace(PUZZLES["gen-10-01"], rules=ThreeMoveRules()), AlwaysPlayer("east,east,south"), MAP
    )
    assert all(p.best_moves == game.solver.best_moves(p.before) for p in game.play())


# The scores


@pytest.mark.parametrize(
    ("text", "level", "answers", "expected"),
    [
        pytest.param(
            CORRIDOR,
            4,
            ["east", "east", "west"],
            (0, 0.5, 0.0, 1),
            id="halfway, then out of answers",
        ),
        pytest.param(CORRIDOR, 4, ["west"] * 8, (0, 0.0, 0.0, 0), id="a lost game"),
        pytest.param(
            "######\n#.A.G#\n######",
            2,
            ["west", "east", "east", "east"],
            (1, 1.0, 0.5, 0),
            id="a slow win",
        ),
        pytest.param(ONE_MOVE, 1, ["jump"], (0, 0.0, 0.0, 1), id="an answer that is no move"),
    ],
)
def test_a_game_is_scored_by_won_progress_spl_and_errors(text, level, answers, expected):
    played = [puzzle(text, level)]
    score = scores(run_benchmark(played, ONLY_MAP, {"p": lambda: ScriptedPlayer(answers)}))
    assert (score["p", "map"].won, score["p", "map"].progress) == expected[:2]
    assert (score["p", "map"].spl, score["p", "map"].errors) == expected[2:]


def test_the_summary_counts_games_won_at_each_level_and_then_the_scores():
    games = len(PUZZLES)
    table = summarize(solved(PUZZLES.values())).splitlines()
    assert table[0].split()[:4] == ["player", "condition", "1", "away"]
    assert table[2].split()[-4:] == [f"{games}/{games}", "1.00", "1.00", "0"]


def test_rows_run_from_random_to_the_solver_with_other_players_below():
    players = {
        "always": lambda: AlwaysPlayer("west"),
        "solver": SolverPlayer,
        "random": RandomPlayer,
    }
    table = summarize(run_benchmark(FIRST_FIVE, ONLY_MAP, players))
    assert [line.split()[0] for line in table.splitlines()[2:]] == ["random", "solver", "always"]


@pytest.mark.parametrize(
    ("moves", "expected"),
    [
        pytest.param(
            [move(input_tokens=100)] * 2,
            "jev: 2 calls, 200 input tokens, 0 output tokens",
            id="calls and tokens",
        ),
        pytest.param(
            [move(input_tokens=100, output_tokens=2, seconds=s) for s in (0.5, 0.5, 3.0)],
            "jev: 3 calls, 300 input tokens, 6 output tokens, 0.50 s per call (median)",
            id="the median wait",
        ),
        pytest.param(
            [move(input_tokens=100, retried=("busy", "busy"))],
            "jev: 1 call, 100 input tokens, 0 output tokens, 2 turned away and retried",
            id="moves turned away",
        ),
    ],
)
def test_usage_counts_the_calls_and_tokens_of_a_paid_player(moves, expected):
    assert usage([record("jev", moves)]) == expected


def test_paid_calls_are_estimated_before_anything_runs_and_leave_out_games_done():
    puzzles = list(PUZZLES.values())
    every_move = sum(p.max_moves for p in puzzles)
    done = {("gen-01-01", "map", "jev")}
    assert estimate_paid_calls(puzzles, ALL, ["jev", "random"]) == every_move * len(ALL)
    assert estimate_paid_calls(puzzles, ALL, ["random"]) == 0
    left = estimate_paid_calls(puzzles, ONLY_MAP, ["jev"], done=done)
    assert left == every_move - PUZZLES["gen-01-01"].max_moves


# Playing, saving and loading


def test_there_is_one_record_per_puzzle_condition_and_player():
    players = {"solver": SolverPlayer, "random": RandomPlayer}
    records = run_benchmark(FIRST_FIVE[:2], ALL, players)
    assert len(records) == 2 * len(ALL) * 2
    assert {r.condition for r in records} == set(CONDITIONS)


def test_games_played_side_by_side_give_the_same_records_in_the_same_order():
    players = {"random": RandomPlayer, "solver": SolverPlayer}
    one_at_a_time = run_benchmark(PUZZLES.values(), ONLY_MAP, players)
    side_by_side = run_benchmark(PUZZLES.values(), ONLY_MAP, players, workers=8)
    assert untimed(side_by_side) == untimed(one_at_a_time)


def test_each_game_is_handed_over_as_soon_as_it_finishes():
    handed: list[GameRecord] = []
    records = solved(FIRST_FIVE, workers=4, on_record=handed.append)
    assert sorted(handed, key=records.index) == records


def test_games_already_done_are_skipped():
    first, second = FIRST_FIVE[:2]
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


def test_a_record_is_saved_as_one_json_line_with_every_move():
    [saved] = solved(FIRST_FIVE[:1])
    line = json.loads(saved.to_json())
    first = line["moves"][0]
    assert (line["player"], line["condition"]) == ("solver", "map")
    assert (sorted(first["options"]), first["optimal"]) == (
        ["east", "north", "south", "west"],
        True,
    )
    assert first["probabilities"] == {first["move"]: 1.0}


def test_saved_games_load_back_unchanged_and_a_cut_off_last_line_is_skipped(tmp_path):
    records = [*solved(FIRST_FIVE[:3]), record(moves=[move(input_tokens=1, retried=("busy",))])]
    path = save(records, tmp_path / "out.jsonl")
    assert load(path) == records
    with path.open("a", encoding="utf-8") as file:
        file.write('{"puzzle": "half a li')
    assert load(path) == records


def test_a_corrupt_line_before_the_last_is_an_error(tmp_path):
    path = save(solved(FIRST_FIVE[:2]), tmp_path / "out.jsonl")
    first, second = path.read_text(encoding="utf-8").splitlines()
    path.write_text(f"{first[:20]}\n{second}\n", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load(path)


@pytest.mark.parametrize(
    ("removed", "name", "expected"),
    [
        pytest.param(
            ("output_tokens", "confidence", "model", "seconds"),
            "seconds",
            None,
            id="newer move fields",
        ),
        pytest.param(("rules",), "rules", "compass", id="rules"),
    ],
)
def test_games_saved_before_a_field_was_added_still_load(tmp_path, removed, name, expected):
    line = json.loads(solved(FIRST_FIVE[:1])[0].to_json())
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
        pytest.param([record()], {"s": "compass"}, None, id="the same run"),
        pytest.param(
            [record(key=("x", "map"))],
            {"s": "compass", "x": "compass"},
            "would not play",
            id="a stray game",
        ),
        pytest.param(
            [replace(record(), rules="two-moves")], {"s": "compass"}, "two-moves", id="other rules"
        ),
    ],
)
def test_a_results_file_can_be_resumed_only_by_the_same_run(loaded, rules_of, expected):
    why = check_same_run(loaded, {("s", "map", "jev")}, rules_of)
    assert (why is None) if expected is None else (expected in why)

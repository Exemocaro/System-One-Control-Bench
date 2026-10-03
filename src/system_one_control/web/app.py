from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from system_one_control.bench import Game, Played
from system_one_control.players import PLAYERS, make_player
from system_one_control.prompts import CONDITIONS, Request
from system_one_control.puzzles import load_puzzles
from system_one_control.world import RULES, Board, make_rules

PAGE = Path(__file__).with_name("index.html")


class NewGame(BaseModel):
    puzzle: str
    player: str
    condition: str
    rules: str = "compass"


def create_app() -> FastAPI:
    puzzles = load_puzzles()
    games: dict[str, Game] = {}
    player_names: dict[str, str] = {}  # by game: the name it was chosen by, as the page lists it
    app = FastAPI(title="System-One Control Bench")

    def find_game(game_id: str) -> Game:
        if game_id not in games:
            raise HTTPException(404, f"no game {game_id!r}")
        return games[game_id]

    @app.get("/", response_class=HTMLResponse)
    def page() -> str:
        return PAGE.read_text(encoding="utf-8")

    @app.get("/api/catalog")
    def catalog() -> dict[str, Any]:
        return {
            "puzzles": [
                {"name": p.name, "description": p.description, "level": p.level}
                for p in puzzles.values()
            ],
            "players": [
                {"name": name, "paid": entry.paid, "compass_only": entry.compass_only}
                for name, entry in PLAYERS.items()
            ],
            "conditions": [
                {"name": c.name, "description": c.description} for c in CONDITIONS.values()
            ],
            "rules": [{"name": name, "description": r.description} for name, r in RULES.items()],
        }

    @app.post("/api/games")
    def new_game(body: NewGame) -> dict[str, Any]:
        for kind, name, known in (
            ("puzzle", body.puzzle, puzzles),
            ("condition", body.condition, CONDITIONS),
            ("player", body.player, PLAYERS),
            ("rules", body.rules, RULES),
        ):
            if name not in known:
                raise HTTPException(404, f"unknown {kind} {name!r}")
        if PLAYERS[body.player].compass_only and body.rules != "compass":
            raise HTTPException(400, f"{body.player} can only play compass rules")
        try:
            player = make_player(body.player)
        except (ImportError, RuntimeError) as error:
            raise HTTPException(400, str(error)) from error
        game_id = uuid4().hex[:8]
        puzzle = replace(puzzles[body.puzzle], rules=make_rules(body.rules))
        games[game_id] = Game(puzzle, player, CONDITIONS[body.condition])
        player_names[game_id] = body.player
        return game_json(game_id, games[game_id], body.player)

    @app.post("/api/games/{game_id}/step")
    def step(game_id: str) -> dict[str, Any]:
        game = find_game(game_id)
        if game.is_over:
            raise HTTPException(409, "the game is over")
        game.play_move()
        return game_json(game_id, game, player_names[game_id])

    @app.post("/api/games/{game_id}/play")
    def play(game_id: str) -> dict[str, Any]:
        game = find_game(game_id)
        game.play()
        return game_json(game_id, game, player_names[game_id])

    return app


def board_json(board: Board) -> dict[str, Any]:
    return {
        "rows": list(board.rows),
        "agent": [board.agent.x, board.agent.y],
        "holding": list(board.holding),
    }


def request_json(request: Request) -> dict[str, Any]:
    return {
        "state": request.state,
        "question": request.question,
        "options": [{"id": o.id, "move": o.move, "text": o.text} for o in request.options],
    }


def played_json(played: Played) -> dict[str, Any]:
    return {
        "number": played.number,
        "before": board_json(played.before),
        "after": board_json(played.after),
        "request": request_json(played.request),
        "choice": {
            "move": played.choice.move,
            "probabilities": played.choice.probabilities,
            "error": played.choice.error,
        },
        "best_moves": list(played.best_moves),
        "optimal": played.optimal,
        "seconds": round(played.seconds, 3),
    }


def game_json(game_id: str, game: Game, player: str) -> dict[str, Any]:
    upcoming = None
    if not game.is_over:
        upcoming = {
            "request": request_json(game.next_request()),
            "best_moves": list(game.best_moves(game.board)),
        }
    return {
        "id": game_id,
        "puzzle": game.puzzle.name,
        "player": player,
        "condition": game.condition.name,
        "rules": game.rules.name,
        "level": game.puzzle.level,
        "fewest_moves": game.puzzle.fewest_moves,
        "max_moves": game.puzzle.max_moves,
        "board": board_json(game.board),
        "won": game.won,
        "over": game.is_over,
        "played": [played_json(played) for played in game.played],
        "next": upcoming,
    }

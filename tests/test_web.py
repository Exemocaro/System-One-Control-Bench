from fastapi.testclient import TestClient

from system_one_control.web.app import create_app

client = TestClient(create_app())


def new_game(puzzle="gen-02-04", player="solver", condition="map", **more):
    body = {"puzzle": puzzle, "player": player, "condition": condition, **more}
    return client.post("/api/games", json=body)


def test_the_page_is_served():
    assert "<title>" in client.get("/").text


def test_the_catalog_lists_puzzles_players_and_conditions():
    catalog = client.get("/api/catalog").json()
    assert "gen-02-04" in [s["name"] for s in catalog["puzzles"]]
    assert {"name": "jev", "paid": True, "compass_only": False} in catalog["players"]
    assert "map" in [p["name"] for p in catalog["conditions"]]
    assert "three-moves" in [r["name"] for r in catalog["rules"]]


def test_a_new_game_shows_the_board_and_what_the_player_will_be_asked():
    game = new_game().json()
    assert game["moves"] == []
    assert game["board"]["rows"][1] == "#..G.....#"  # the goal is up and to the left
    assert game["next"]["best_moves"] == ["north", "west"]
    assert "#...A....#" in game["next"]["request"]["state"]


def test_one_move_plays_one_move():
    game_id = new_game().json()["id"]
    game = client.post(f"/api/games/{game_id}/move").json()
    assert len(game["moves"]) == 1
    assert game["moves"][0]["choice"]["move"] == "north"
    assert game["moves"][0]["optimal"]


def test_play_runs_the_game_to_the_end():
    game_id = new_game().json()["id"]
    game = client.post(f"/api/games/{game_id}/play").json()
    assert game["won"] and game["over"]
    assert len(game["moves"]) == 2
    assert game["next"] is None


def test_moving_a_finished_game_is_refused():
    game_id = new_game().json()["id"]
    client.post(f"/api/games/{game_id}/play")
    assert client.post(f"/api/games/{game_id}/move").status_code == 409


def test_unknown_names_are_reported():
    response = new_game(puzzle="nowhere")
    assert response.status_code == 404
    assert "nowhere" in response.json()["detail"]


def test_a_game_can_be_played_under_other_rules():
    game = new_game(rules="two-moves").json()
    assert game["rules"] == "two-moves"
    assert game["fewest_moves"] == 1 and game["level"] == 2
    assert len(game["next"]["request"]["options"]) == 16


def test_a_compass_only_player_is_refused_other_rules():
    assert new_game(player="greedy", rules="two-moves").status_code == 400


def test_a_game_shows_the_player_by_the_name_it_was_chosen_by():
    assert new_game(player="random").json()["player"] == "random"

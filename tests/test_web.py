from fastapi.testclient import TestClient

from system_one_control.web.app import create_app

client = TestClient(create_app())


def new_game(scenario="straight", player="solver", condition="map"):
    return client.post(
        "/api/games", json={"scenario": scenario, "player": player, "condition": condition}
    )


def test_the_page_is_served():
    assert "<title>" in client.get("/").text


def test_the_catalog_lists_scenarios_players_and_conditions():
    catalog = client.get("/api/catalog").json()
    assert "key-first" in [s["name"] for s in catalog["scenarios"]]
    assert {"name": "jev", "paid": True} in catalog["players"]
    assert "map" in [p["name"] for p in catalog["conditions"]]


def test_a_new_game_shows_the_board_and_what_the_player_will_be_asked():
    game = new_game().json()
    assert game["steps"] == []
    assert game["board"]["rows"][1] == "#..G.#"
    assert game["next"]["best_moves"] == ["east"]
    assert "#A.G.#" in game["next"]["request"]["state"]


def test_one_step_plays_one_move():
    game_id = new_game().json()["id"]
    game = client.post(f"/api/games/{game_id}/step").json()
    assert len(game["steps"]) == 1
    assert game["steps"][0]["choice"]["move"] == "east"
    assert game["steps"][0]["optimal"]


def test_play_runs_the_game_to_the_end():
    game_id = new_game().json()["id"]
    game = client.post(f"/api/games/{game_id}/play").json()
    assert game["won"] and game["over"]
    assert len(game["steps"]) == 2
    assert game["next"] is None


def test_stepping_a_finished_game_is_refused():
    game_id = new_game().json()["id"]
    client.post(f"/api/games/{game_id}/play")
    assert client.post(f"/api/games/{game_id}/step").status_code == 409


def test_unknown_names_are_reported():
    response = new_game(scenario="nowhere")
    assert response.status_code == 404
    assert "nowhere" in response.json()["detail"]

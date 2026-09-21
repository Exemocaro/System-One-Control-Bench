"""Loading API keys from the environment and from a .env file."""

import pytest

from system_one_control.credentials import CredentialError, load_api_key, read_dotenv


def test_a_real_environment_variable_wins_over_the_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("DEMO_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("DEMO_KEY", "from-environment")
    assert load_api_key("DEMO_KEY", dotenv_path=env_file) == "from-environment"


def test_the_file_is_used_when_the_variable_is_absent(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("DEMO_KEY=from-file\n", encoding="utf-8")
    monkeypatch.delenv("DEMO_KEY", raising=False)
    assert load_api_key("DEMO_KEY", dotenv_path=env_file) == "from-file"


def test_several_names_are_tried_in_order(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("SECOND_KEY=second\n", encoding="utf-8")
    monkeypatch.delenv("FIRST_KEY", raising=False)
    monkeypatch.delenv("SECOND_KEY", raising=False)
    assert load_api_key("FIRST_KEY", "SECOND_KEY", dotenv_path=env_file) == "second"


def test_a_missing_key_names_every_variable_that_was_tried(tmp_path, monkeypatch):
    monkeypatch.delenv("FIRST_KEY", raising=False)
    monkeypatch.delenv("SECOND_KEY", raising=False)
    with pytest.raises(CredentialError, match="FIRST_KEY.*SECOND_KEY"):
        load_api_key("FIRST_KEY", "SECOND_KEY", dotenv_path=tmp_path / "absent.env")


def test_quotes_comments_and_blank_lines_are_handled(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# a comment\n\nQUOTED=\"value\"\nSINGLE='other'\nexport EXPORTED=third\n",
        encoding="utf-8",
    )
    parsed = read_dotenv(env_file)
    assert parsed == {"QUOTED": "value", "SINGLE": "other", "EXPORTED": "third"}


def test_a_value_containing_an_equals_sign_survives(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("TOKEN=abc=def==\n", encoding="utf-8")
    assert read_dotenv(env_file)["TOKEN"] == "abc=def=="


def test_an_absent_file_is_not_an_error(tmp_path):
    assert read_dotenv(tmp_path / "nothing-here") == {}

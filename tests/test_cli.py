"""CLI smoke test."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from deckforge_core.cli.app import app
from deckforge_core.tools.generate_corpus import build_deck

runner = CliRunner()


def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "DeckForge" in result.stdout


def test_about_command():
    result = runner.invoke(app, ["about"])
    assert result.exit_code == 0
    assert "Format Pack" in result.stdout


def test_no_args_shows_help():
    result = runner.invoke(app)
    # typer prints usage to stderr and exits 2 with no_args_is_help
    assert result.exit_code in (0, 2)
    assert "Usage" in (result.stdout + result.stderr)


@pytest.fixture()
def cli_env(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for i in range(2):
        build_deck(corpus / f"deck_{i:02d}.pptx", i, seed=20240316)
    monkeypatch.setenv("DECKFORGE_DATA_DIR", str(tmp_path))
    return tmp_path


def test_learn_command(cli_env):
    result = runner.invoke(app, ["learn", str(cli_env / "corpus"), "--name", "demo"])
    assert result.exit_code == 0
    assert "demo" in result.stdout
    assert (cli_env / "packs" / "demo" / "pack.json").is_file()


def test_make_command(cli_env):
    result = runner.invoke(app, ["learn", str(cli_env / "corpus"), "--name", "demo"])
    assert result.exit_code == 0
    out = cli_env / "deck"
    result = runner.invoke(
        app,
        ["make", "Roadmap", "--pack", "demo", "--slides", "5", "--out", str(out)],
    )
    assert result.exit_code == 0
    assert "slides" in result.stdout
    assert (cli_env / "deck.pptx").is_file()


def test_outline_command(cli_env):
    runner.invoke(app, ["learn", str(cli_env / "corpus"), "--name", "demo"])
    result = runner.invoke(app, ["outline", "Roadmap", "--pack", "demo", "--slides", "3"])
    assert result.exit_code == 0
    assert "title" in result.stdout


def test_packs_list_show_delete(cli_env):
    runner.invoke(app, ["learn", str(cli_env / "corpus"), "--name", "demo"])
    result = runner.invoke(app, ["packs", "list"])
    assert result.exit_code == 0
    assert "demo" in result.stdout
    result = runner.invoke(app, ["packs", "show", "demo"])
    assert result.exit_code == 0
    assert "archetypes" in result.stdout
    result = runner.invoke(app, ["packs", "delete", "demo", "--yes"])
    assert result.exit_code == 0
    assert not (cli_env / "packs" / "demo").exists()


def test_settings_set_list_cli(cli_env):
    result = runner.invoke(app, ["settings", "set", "local_only", "false"])
    assert result.exit_code == 0
    result = runner.invoke(app, ["settings", "get", "local_only"])
    assert result.exit_code == 0
    assert "false" in result.stdout
    result = runner.invoke(app, ["settings", "unset", "local_only"])
    assert result.exit_code == 0
    result = runner.invoke(app, ["settings", "get", "local_only"])
    assert "true" in result.stdout

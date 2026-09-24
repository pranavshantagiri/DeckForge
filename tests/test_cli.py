"""CLI smoke test."""

from __future__ import annotations

from typer.testing import CliRunner

from deckforge_core.cli.app import app

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

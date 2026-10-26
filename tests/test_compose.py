"""`compose` (template + per-slide content) tests."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from deckforge_core.cli.app import app
from deckforge_core.modes.compose import run_compose
from deckforge_core.tools.generate_corpus import build_deck

runner = CliRunner()


@pytest.fixture()
def template(tmp_path):
    pptx_path, _ = build_deck(tmp_path / "template.pptx", 3, seed=20240316)
    return pptx_path


@pytest.fixture()
def content_file(tmp_path):
    def write(slides):
        path = tmp_path / "content.json"
        path.write_text(json.dumps({"slides": slides}), encoding="utf-8")
        return path

    return write


def test_compose_basic(template, content_file, tmp_path):
    content = content_file(
        [
            {"title": "Q3 Review", "kicker": "Finance", "body": ["Revenue up 12%"]},
            {"title": "Growth Drivers", "col_a": ["Product", "Pricing"], "col_b": ["Channel"]},
            {"title": "Roadmap", "card_1": "Ship beta", "card_2": "Hiring"},
            {"title": "Takeaways", "bullets": ["Focus", "Speed"]},
        ]
    )
    out = tmp_path / "out"
    result = run_compose(str(template), str(content), str(out))
    assert (tmp_path / "out.pptx").is_file()
    assert result.slide_count == 4


def test_compose_recycles_layout_beyond_template(template, content_file, tmp_path):
    slides = [{"title": f"Slide {i}", "body": "text"} for i in range(16)]
    out = tmp_path / "long"
    result = run_compose(str(template), str(content_file(slides)), str(out))
    assert result.slide_count == 16
    assert any("recycle" in note for note in result.notes)


def test_compose_missing_template(content_file, tmp_path):
    with pytest.raises(Exception, match="template not found"):
        run_compose(str(tmp_path / "nope.pptx"), str(content_file([{"title": "x"}])), str(tmp_path / "o"))


def test_compose_bad_json(template, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(Exception, match="cannot read content JSON"):
        run_compose(str(template), str(bad), str(tmp_path / "o"))


def test_compose_unknown_archetype(template, content_file, tmp_path):
    content = content_file([{"title": "x", "archetype": "not-an-archetype"}])
    with pytest.raises(Exception, match="unknown archetype"):
        run_compose(str(template), str(content), str(tmp_path / "o"))


def test_compose_empty(content_file, template, tmp_path):
    with pytest.raises(Exception, match="no slides"):
        run_compose(str(template), str(content_file([])), str(tmp_path / "o"))


def test_compose_cli(template, content_file, tmp_path, monkeypatch):
    monkeypatch.setenv("DECKFORGE_DATA_DIR", str(tmp_path / "data"))
    content = content_file(
        [
            {"title": "Kickoff", "subtitle": "Scope", "body": ["One", "Two"]},
            {"title": "Next", "statement": "Ship it"},
        ]
    )
    result = runner.invoke(app, ["compose", str(template), str(content)])
    assert result.exit_code == 0, result.stderr
    assert "template-composed.pptx" in result.stdout
    assert (tmp_path / "data" / "decks" / "template-composed.pptx").is_file()

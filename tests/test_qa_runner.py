"""Top-level QA runner: backend resolution, thumbnails, no-exception guarantee."""

from __future__ import annotations

import os
from pathlib import Path

from deckforge_core.providers.render import RenderBackend, RendererAutodetect
from deckforge_core.qa.runner import run_qa
from deckforge_core.schemas.archetypes import Archetype
from deckforge_core.schemas.blueprints import (
    Blueprint,
    BlueprintLibrary,
    ContentKind,
    SlotDef,
    SlotRegion,
)
from deckforge_core.schemas.deck_plan import DeckPlan, SlidePlan, SlotValue


def _slot(name, x, y, w, h, style="body", kinds=None):
    return SlotDef(
        name=name,
        kinds=kinds or [ContentKind.TEXT],
        region=SlotRegion(x=x, y=y, w=w, h=h),
        style=style,
    )


def _library() -> BlueprintLibrary:
    return BlueprintLibrary(
        [
            Blueprint(
                id="two-column-text",
                archetype=Archetype.TWO_COLUMN_TEXT,
                slots=[
                    _slot("title", 0.06, 0.05, 0.88, 0.1, "h2"),
                    _slot("body", 0.08, 0.28, 0.42, 0.4),
                ],
            )
        ]
    )


def _clean_plan() -> DeckPlan:
    return DeckPlan(
        title="Runner deck",
        aspect_ratio="16:9",
        pack="demo",
        slides=[
            SlidePlan(
                n=1,
                archetype="two-column-text",
                title="Runner deck",
                slots={
                    "title": SlotValue(text="Runner deck"),
                    "body": SlotValue(text="A comfortable amount of copy."),
                },
            )
        ],
    )


def test_run_qa_none_backend_deterministic_only(canonical_pack, tmp_path):
    out_dir = tmp_path / "out"
    report = run_qa(
        _clean_plan(), canonical_pack, _library(),
        render_backend="none", out_dir=out_dir,
    )
    assert report.rendered is False
    assert report.errors_total() == 0
    assert len(report.slides) == 1
    assert report.slides[0].thumbnail_path is None
    assert out_dir.is_dir()


def test_run_qa_unknown_backend_falls_back_quietly(canonical_pack, tmp_path):
    report = run_qa(
        _clean_plan(), canonical_pack, _library(),
        render_backend="not-a-backend", out_dir=tmp_path / "out",
    )
    assert report.rendered is False
    assert report.errors_total() == 0
    assert any("unavailable" in entry for entry in report.qa_log)


def test_run_qa_auto_resolves_and_renders_when_available(canonical_pack, tmp_path):
    out_dir = tmp_path / "out"
    detector = RendererAutodetect()
    resolved = detector.resolve(RenderBackend.AUTO.value)
    if resolved.backend == RenderBackend.NONE:
        report = run_qa(
            _clean_plan(), canonical_pack, _library(),
            render_backend="auto", out_dir=out_dir, max_iters=1,
        )
        assert report.rendered is False
        assert report.errors_total() == 0
    elif os.environ.get("DECKFORGE_TEST_COM_RENDER") == "1":
        report = run_qa(
            _clean_plan(), canonical_pack, _library(),
            render_backend="auto", out_dir=out_dir, max_iters=1,
        )
        assert report.rendered is True
        assert (out_dir / "renders").is_dir()
        thumbnails = [s.thumbnail_path for s in report.slides if s.thumbnail_path]
        assert thumbnails
        assert all(Path(p).exists() for p in thumbnails)
        assert report.errors_total() == 0
    else:
        # A real backend resolved (PowerPoint/LibreOffice) but live office
        # automation is not opted in: assert resolution without invoking it.
        assert resolved.backend in (
            RenderBackend.POWERPOINT_COM,
            RenderBackend.LIBREOFFICE,
        )
        report = run_qa(
            _clean_plan(), canonical_pack, _library(),
            render_backend="none", out_dir=out_dir, max_iters=1,
        )
        assert report.rendered is False
        assert report.errors_total() == 0


def test_run_qa_never_raises_for_broken_pack(canonical_pack, tmp_path):
    # A plan whose blueprint is missing entirely must not escape as an exception.
    plan = DeckPlan(
        title="Broken",
        aspect_ratio="16:9",
        pack="demo",
        slides=[SlidePlan(n=1, archetype="no-such-archetype", title="fallback")],
    )
    report = run_qa(plan, canonical_pack, _library(), render_backend="none", out_dir=tmp_path / "out")
    assert isinstance(report.slides, list)
    assert report.rendered is False

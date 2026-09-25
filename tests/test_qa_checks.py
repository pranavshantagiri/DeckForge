"""Deterministic QA checks (Workstream H): plan-vs-blueprint geometry and copy."""

from __future__ import annotations

from deckforge_core.qa.checks import (
    check_contrast,
    check_empty_placeholders,
    check_min_font,
    check_off_grid,
    check_overflow,
    check_overlap,
    contrast_ratio,
    relative_luminance,
    run_deterministic,
)
from deckforge_core.schemas.archetypes import Archetype
from deckforge_core.schemas.blueprints import (
    Blueprint,
    BlueprintLibrary,
    ContentKind,
    SlotDef,
    SlotRegion,
)
from deckforge_core.schemas.deck_plan import DeckPlan, SlidePlan, SlotValue
from deckforge_core.schemas.pack import (
    ColorPalette,
    FontPair,
    PaletteColor,
    StyleProfile,
    TypeScale,
    TypeScaleEntry,
)
from deckforge_core.schemas.qa import IssueSeverity, QACheckType


def _slot(name, x, y, w, h, style="body", kinds=None, optional=False):
    return SlotDef(
        name=name,
        kinds=kinds or [ContentKind.TEXT],
        region=SlotRegion(x=x, y=y, w=w, h=h),
        style=style,
        optional=optional,
    )


def _library(blueprints: list[Blueprint]) -> BlueprintLibrary:
    return BlueprintLibrary(blueprints)


def _plan(slides: list[SlidePlan]) -> DeckPlan:
    return DeckPlan(title="QA checks", aspect_ratio="16:9", pack="demo", slides=slides)


# --------------------------------------------------------------------------- #
# Overflow
# --------------------------------------------------------------------------- #
def test_overflow_flags_overlong_body(canonical_style):
    library = _library(
        [
            Blueprint(
                id="two-column-text",
                archetype=Archetype.TWO_COLUMN_TEXT,
                slots=[_slot("col_a_body", 0.08, 0.28, 0.42, 0.12, "body")],
            )
        ]
    )
    plan = _plan(
        [
            SlidePlan(
                n=5,
                archetype="two-column-text",
                slots={
                    "col_a_body": SlotValue(
                        text=" ".join(["agglomeration jargon conversation"] * 250)
                    )
                },
            )
        ]
    )
    issues = check_overflow(canonical_style, plan, library)
    assert len(issues) == 1
    issue = issues[0]
    assert issue.check == QACheckType.OVERFLOW
    assert issue.severity == IssueSeverity.ERROR
    assert issue.slide_n == 5
    assert issue.detail and issue.detail["slot"] == "col_a_body"


def test_overflow_silent_for_short_text(canonical_style):
    library = _library(
        [
            Blueprint(
                id="two-column-text",
                archetype=Archetype.TWO_COLUMN_TEXT,
                slots=[_slot("col_a_body", 0.08, 0.28, 0.42, 0.12, "body")],
            )
        ]
    )
    plan = _plan(
        [
            SlidePlan(
                n=1,
                archetype="two-column-text",
                slots={"col_a_body": SlotValue(text="A short, comfortable line.")},
            )
        ]
    )
    assert check_overflow(canonical_style, plan, library) == []


# --------------------------------------------------------------------------- #
# Overlap
# --------------------------------------------------------------------------- #
def test_overlap_flags_stacked_regions(canonical_style):
    library = _library(
        [
            Blueprint(
                id="stacked",
                archetype=Archetype.TWO_COLUMN_TEXT,
                slots=[
                    _slot("top", 0.1, 0.3, 0.5, 0.5),
                    _slot("bottom", 0.2, 0.2, 0.5, 0.5),
                ],
            )
        ]
    )
    plan = _plan(
        [
            SlidePlan(
                n=2,
                archetype="stacked",
                slots={
                    "top": SlotValue(text="first"),
                    "bottom": SlotValue(text="second"),
                },
            )
        ]
    )
    issues = check_overlap(canonical_style, plan, library)
    assert len(issues) == 1
    assert issues[0].check == QACheckType.OVERLAP
    assert issues[0].severity == IssueSeverity.ERROR
    assert issues[0].slide_n == 2


def test_overlap_ignores_clear_regions(canonical_style):
    library = _library(
        [
            Blueprint(
                id="side-by-side",
                archetype=Archetype.TWO_COLUMN_TEXT,
                slots=[
                    _slot("left", 0.05, 0.05, 0.4, 0.5),
                    _slot("right", 0.55, 0.05, 0.4, 0.5),
                ],
            )
        ]
    )
    plan = _plan(
        [
            SlidePlan(
                n=1,
                archetype="side-by-side",
                slots={
                    "left": SlotValue(text="Left column"),
                    "right": SlotValue(text="Right column"),
                },
            )
        ]
    )
    assert check_overlap(canonical_style, plan, library) == []


# --------------------------------------------------------------------------- #
# Off-grid
# --------------------------------------------------------------------------- #
def test_off_grid_flags_misaligned_slot(canonical_style):
    # canonical grid: 12 columns, gutter 0.02, margins 0.06 -> col width 0.055
    library = _library(
        [
            Blueprint(
                id="grid",
                archetype=Archetype.TWO_COLUMN_TEXT,
                slots=[
                    _slot("bad", 0.12, 0.3, 0.4, 0.3),
                    _slot("good", 0.06, 0.7, 0.205, 0.1),
                ],
            )
        ]
    )
    plan = _plan(
        [
            SlidePlan(
                n=3,
                archetype="grid",
                slots={
                    "bad": SlotValue(text="off the grid"),
                    "good": SlotValue(text="aligned"),
                },
            )
        ]
    )
    issues = check_off_grid(canonical_style, plan, library)
    assert len(issues) == 1
    assert issues[0].check == QACheckType.OFF_GRID
    assert issues[0].severity == IssueSeverity.WARNING
    assert issues[0].detail and issues[0].detail["slot"] == "bad"


# --------------------------------------------------------------------------- #
# Empty placeholders
# --------------------------------------------------------------------------- #
def test_empty_required_placeholder_flagged(canonical_style):
    library = _library(
        [
            Blueprint(
                id="content",
                archetype=Archetype.TWO_COLUMN_TEXT,
                slots=[
                    _slot("body", 0.06, 0.06, 0.4, 0.4),
                    _slot("optional_card", 0.5, 0.06, 0.4, 0.3, optional=True),
                ],
            )
        ]
    )
    plan = _plan(
        [SlidePlan(n=1, archetype="content", slots={"optional_card": SlotValue(text="filled")})]
    )
    issues = check_empty_placeholders(canonical_style, plan, library)
    assert len(issues) == 1
    assert issues[0].check == QACheckType.EMPTY_PLACEHOLDER
    assert issues[0].severity == IssueSeverity.WARNING
    assert issues[0].detail and issues[0].detail["slot"] == "body"


# --------------------------------------------------------------------------- #
# Min font
# --------------------------------------------------------------------------- #
def _micro_style() -> StyleProfile:
    return StyleProfile(
        palette=ColorPalette(
            colors=[
                PaletteColor(role="bg", hex="#FFFFFF"),
                PaletteColor(role="text", hex="#111111"),
            ]
        ),
        fonts=FontPair(heading="Arial", body="Arial"),
        type_scale=TypeScale(
            entries=[
                TypeScaleEntry(name="h1", size_pt=28, weight="bold"),
                TypeScaleEntry(name="body", size_pt=12),
                TypeScaleEntry(name="micro", size_pt=6),
            ]
        ),
    )


def test_min_font_flags_tiny_size():
    style = _micro_style()
    library = _library(
        [
            Blueprint(
                id="tiny",
                archetype=Archetype.TWO_COLUMN_TEXT,
                slots=[_slot("micro_text", 0.06, 0.06, 0.4, 0.3, "micro")],
            )
        ]
    )
    plan = _plan(
        [SlidePlan(n=1, archetype="tiny", slots={"micro_text": SlotValue(text="fine print")})]
    )
    issues = check_min_font(style, plan, library)
    assert len(issues) == 1
    assert issues[0].check == QACheckType.MIN_FONT
    assert issues[0].detail and issues[0].detail["size_pt"] == 6


# --------------------------------------------------------------------------- #
# Contrast
# --------------------------------------------------------------------------- #
def test_contrast_math_unit():
    assert abs(contrast_ratio("#FFFFFF", "#000000") - 21.0) < 0.01
    assert abs(contrast_ratio("#C4472F", "#FFFFFF") - 4.90) < 0.05
    assert relative_luminance("#FFFFFF") > 0.99
    assert relative_luminance("#000000") < 1e-3


def test_canonical_palette_contrast_passes(canonical_style):
    plan = _plan([SlidePlan(n=1, archetype="two-column-text", slots={})])
    issues = check_contrast(canonical_style, plan)
    assert not [i for i in issues if i.check == QACheckType.CONTRAST]


def test_contrast_flags_low_contrast_pair():
    style = StyleProfile(
        palette=ColorPalette(
            colors=[
                PaletteColor(role="bg", hex="#FFFFFF"),
                PaletteColor(role="text", hex="#C0C0C0"),
            ]
        ),
        fonts=FontPair(heading="Arial", body="Arial"),
        type_scale=TypeScale(
            entries=[
                TypeScaleEntry(name="h1", size_pt=28, weight="bold"),
                TypeScaleEntry(name="body", size_pt=16),
            ]
        ),
    )
    plan = _plan([SlidePlan(n=1, archetype="two-column-text", slots={})])
    issues = check_contrast(style, plan)
    low = [i for i in issues if i.check == QACheckType.CONTRAST]
    assert low
    assert all(i.severity == IssueSeverity.WARNING for i in low)


# --------------------------------------------------------------------------- #
# Fan-in
# --------------------------------------------------------------------------- #
def test_run_deterministic_groups_by_slide(canonical_style):
    library = _library(
        [
            Blueprint(
                id="two-column-text",
                archetype=Archetype.TWO_COLUMN_TEXT,
                slots=[_slot("col_a_body", 0.08, 0.28, 0.42, 0.12, "body")],
            )
        ]
    )
    plan = _plan(
        [
            SlidePlan(
                n=1,
                archetype="two-column-text",
                slots={
                    "col_a_body": SlotValue(
                        text=" ".join(["agglomeration jargon conversation"] * 250)
                    )
                },
            ),
            SlidePlan(
                n=2,
                archetype="two-column-text",
                slots={"col_a_body": SlotValue(text="Short, clean copy.")},
            ),
        ]
    )
    grouped = run_deterministic(canonical_style, plan, library)
    assert set(grouped.keys()) == {1, 2}
    assert any(i.check == QACheckType.OVERFLOW for i in grouped[1])
    assert not any(i.check == QACheckType.OVERFLOW for i in grouped[2])

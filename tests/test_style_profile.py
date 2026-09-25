"""Style profile extraction (Workstream B): given explicitly styled decks,
the profile must recover fonts, palette roles, margins and type scale."""

from __future__ import annotations

from deckforge_core.analysis import style_from_decks
from deckforge_core.schemas.extracted import (
    ExtractedDeck,
    ExtractedParagraph,
    ExtractedShape,
    ExtractedSlide,
    ExtractedTextRun,
)

GEORGIA = "Georgia"
ARIAL = "Arial"
INK = "#1F2937"  # darkest -> text
MUTED = "#6B7280"
PAPER = "#FAFAF7"  # brightest, fills -> bg


def _run(text: str, size: float, font: str, color: str, *, bold: bool = False) -> ExtractedTextRun:
    return ExtractedTextRun(text=text, size_pt=size, font_name=font, bold=bold, color_hex=color)


def _para(text: str, size: float, font: str, color: str, *, bold: bool = False) -> ExtractedParagraph:
    return ExtractedParagraph(runs=[_run(text, size, font, color, bold=bold)])


def _shape(x: float, y: float, w: float, h: float, paras: list[ExtractedParagraph]) -> ExtractedShape:
    return ExtractedShape(
        shape_type="TEXT_BOX",
        x=x,
        y=y,
        w=w,
        h=h,
        fill_hex=PAPER,
        text=paras,
    )


def _synthetic_deck() -> ExtractedDeck:
    s1 = ExtractedSlide(
        index=1,
        shapes=[
            _shape(0.1, 0.08, 0.8, 0.08, [_para("Q3 2026", 12, GEORGIA, MUTED, bold=True)]),
            _shape(0.1, 0.2, 0.8, 0.12, [_para("Building the category", 30, GEORGIA, INK, bold=True)]),
            _shape(0.1, 0.35, 0.8, 0.55, [_para("A working document for the whole planning team.", 16, ARIAL, INK)]),
        ],
    )
    s2 = ExtractedSlide(
        index=2,
        shapes=[
            _shape(0.1, 0.08, 0.8, 0.08, [_para("AGENDA", 12, GEORGIA, MUTED, bold=True)]),
            _shape(0.1, 0.42, 0.8, 0.12, [_para("The user problem", 26, GEORGIA, INK, bold=True)]),
        ],
    )
    s3 = ExtractedSlide(
        index=3,
        shapes=[
            _shape(0.1, 0.08, 0.8, 0.08, [_para("The playbook for a faster ship", 20, GEORGIA, INK, bold=True)]),
            _shape(
                0.1,
                0.2,
                0.8,
                0.7,
                [
                    _para("Our customers ask for faster onboarding every week.", 16, ARIAL, INK),
                    _para("The product team ships new guidance each month.", 16, ARIAL, INK),
                    _para("Support volumes keep growing across every region.", 16, ARIAL, INK),
                    _para("Self-serve flows now answer the simplest requests.", 16, ARIAL, INK),
                    _para("Retention improves when people reach value quickly.", 16, ARIAL, INK),
                    _para("Every launch ships with a fresh set of analytics.", 16, ARIAL, INK),
                ],
            ),
        ],
    )
    return ExtractedDeck(
        path="synthetic.pptx",
        slide_count=3,
        size_emu=(12192000, 6858000),
        slides=[s1, s2, s3],
    )


def test_fonts_recovered():
    profile = style_from_decks([_synthetic_deck()])
    assert profile.fonts.heading == GEORGIA
    assert profile.fonts.body == ARIAL
    assert profile.fonts.heading_usage_pct > 0
    assert profile.fonts.body_usage_pct > 0


def test_palette_roles_from_explicit_colours():
    profile = style_from_decks([_synthetic_deck()])
    assert profile.palette.has("text")
    assert profile.palette.has("bg")
    assert profile.palette.has("muted-text")
    assert profile.palette.hex("text") == INK
    assert profile.palette.hex("bg") == PAPER
    assert sum(c.usage_pct for c in profile.palette.colors) <= 100.5
    assert profile.palette.has("text") and profile.palette.hex("text") != profile.palette.hex("bg")


def test_margins_recovered():
    profile = style_from_decks([_synthetic_deck()])
    assert profile.margins.left == 0.1
    assert profile.margins.top == 0.08


def test_type_scale_modal_body_and_kicker():
    profile = style_from_decks([_synthetic_deck()])
    assert profile.type_scale.entry("body").size_pt == 16
    assert profile.type_scale.entry("kicker").size_pt == 12
    assert profile.type_scale.entry("kicker").caps == "upper"
    h1 = profile.type_scale.entry("h1").size_pt
    assert h1 >= 20 and h1 > 16


def test_profile_round_trips_through_dump_reload():
    profile = style_from_decks([_synthetic_deck()])
    again = profile.__class__.model_validate(profile.model_dump(mode="json"))
    assert again.model_dump(mode="json") == profile.model_dump(mode="json")


def test_confidence_is_anchored():
    profile = style_from_decks([_synthetic_deck()])
    assert 0.0 < profile.confidence.overall <= 1.0
    assert profile.confidence.layout > 0.0
    assert profile.confidence.palette > 0.0

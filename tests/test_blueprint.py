"""Blueprint derivation (Workstream B): known slide geometries must become
slot regions that match the source shapes, stay inside canonical vocabularies,
and declare a portrait alternate for real columnar layouts."""

from __future__ import annotations

from deckforge_core.analysis.blueprint import blueprints_from_slides
from deckforge_core.schemas.blueprints import ContentKind
from deckforge_core.schemas.extracted import (
    ExtractedParagraph,
    ExtractedShape,
    ExtractedSlide,
    ExtractedTextRun,
)
from deckforge_core.schemas.slot_vocabulary import has_vocabulary, slots_for


def _para(text: str, size: float = 14.0) -> ExtractedParagraph:
    return ExtractedParagraph(runs=[ExtractedTextRun(text=text, size_pt=size)])


def _text_shape(x: float, y: float, w: float, h: float, text: str, size: float = 14.0) -> ExtractedShape:
    return ExtractedShape(shape_type="TEXT_BOX", x=x, y=y, w=w, h=h, text=[_para(text, size)])


def _big_number_slide(index: int, value: str) -> ExtractedSlide:
    return ExtractedSlide(
        index=index,
        shapes=[
            _text_shape(0.1, 0.25, 0.8, 0.38, value, size=72),
            _text_shape(0.1, 0.68, 0.8, 0.1, "Users up year over year", size=16),
        ],
    )


def _two_column_slide(index: int, left: str, right: str) -> ExtractedSlide:
    return ExtractedSlide(
        index=index,
        shapes=[
            _text_shape(0.05, 0.2, 0.43, 0.6, "The left column says this about the topic.", size=14),
            _text_shape(0.52, 0.2, 0.43, 0.6, left),
            _text_shape(0.05, 0.2, 0.43, 0.6, "The right column says that about the topic.", size=14),
            _text_shape(0.52, 0.2, 0.43, 0.6, right),
        ],
    )


def test_big_number_blueprint_matches_source_geometry():
    group = [
        _big_number_slide(3, "91"),
        _big_number_slide(4, "38%"),
        _big_number_slide(5, "2.4x"),
    ]
    library = blueprints_from_slides({"big-number": group})
    assert library.archetypes() == ["big-number"]
    b = library.require("big-number")
    assert b.id == "big-number"
    assert set(n for n, _ in [(s.name, s) for s in b.slots]) == {"number", "caption"}
    number = b.slot("number")
    caption = b.slot("caption")
    assert abs(number.region.x - 0.1) < 0.03
    assert abs(number.region.y - 0.25) < 0.03
    assert abs(number.region.w - 0.8) < 0.03
    assert abs(caption.region.y - 0.68) < 0.03
    assert ContentKind.NUMBER in number.kinds
    assert ContentKind.TEXT in caption.kinds


def test_big_number_text_limits_are_sane():
    group = [_big_number_slide(3, "91"), _big_number_slide(4, "2.4x")]
    b = blueprints_from_slides({"big-number": group}).require("big-number")
    for slot in b.slots:
        limits = slot.text_limits
        assert limits is not None
        assert limits.min_chars <= limits.max_chars
        assert limits.min_words <= limits.max_words
        assert limits.max_chars >= 20
        assert limits.max_lines >= 1


def test_slot_names_in_canonical_vocabulary():
    group = [_big_number_slide(3, "91"), _big_number_slide(4, "2.4x")]
    b = blueprints_from_slides({"big-number": group}).require("big-number")
    assert has_vocabulary("big-number")
    for slot in b.slots:
        kinds = slots_for("big-number").kinds_for(slot.name)
        assert kinds is not None
        assert all(k in kinds for k in slot.kinds)


def test_two_column_blueprint_stacks_columns_for_portrait():
    group = [
        _two_column_slide(6, "First column has a heading worth reading here.", "Second column shares more detail here."),
        _two_column_slide(7, "First column has a heading worth reading there.", "Second column shares more detail there."),
    ]
    library = blueprints_from_slides({"two-column-text": group})
    b, default = library.resolve("two-column-text", "16:9")
    assert b.id == "two-column-text"
    assert len(default) >= 2

    b, portrait = library.resolve("two-column-text", "portrait")
    assert len(portrait) >= 2
    left = next(s for s in portrait if s.name == "col_a_body")
    right = next(s for s in portrait if s.name == "col_b_body")
    assert left.region.y + left.region.h <= right.region.y + 0.01
    assert abs(left.region.x - (0.5 - left.region.w / 2)) < 0.02
    assert abs(right.region.x - (0.5 - right.region.w / 2)) < 0.02


def test_blueprint_word_totals_bounded():
    group = [_big_number_slide(3, "91"), _big_number_slide(4, "38%"), _big_number_slide(5, "2.4x")]
    b = blueprints_from_slides({"big-number": group}).require("big-number")
    assert b.min_words_total >= 0
    assert b.max_words_total >= b.min_words_total
    assert b.max_words_total >= 20

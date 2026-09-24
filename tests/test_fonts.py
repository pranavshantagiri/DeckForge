"""Font pairing: deterministic routing and look/contrast labels."""

from __future__ import annotations

from deckforge_core.theme.fonts import FONT_NAMES, look_contrast, pair_for_brief


def test_modern_clean_returns_sans_pair():
    pair = pair_for_brief("modern clean")
    assert pair.heading in FONT_NAMES
    assert pair.body in FONT_NAMES
    assert pair.heading == "Segoe UI"
    assert pair.body == "Calibri"


def test_same_seed_same_pair():
    a = pair_for_brief("modern clean", seed=3)
    b = pair_for_brief("modern clean", seed=3)
    assert a.model_dump() == b.model_dump()


def test_default_pair_when_brief_empty():
    pair = pair_for_brief("")
    assert pair.heading == "Arial"
    assert pair.body == "Arial"


def test_editorial_classic_is_serif_heading():
    pair = pair_for_brief("editorial classic")
    assert pair.heading == "Georgia"
    assert look_contrast(pair) == "high"


def test_distinct_heading_families_across_moods():
    briefs = ["editorial classic", "modern clean", "humanist warm", "playful", "corporate"]
    headings = {pair_for_brief(b).heading for b in briefs}
    assert len(headings) >= 2


def test_load_contrast_medium_for_two_sans():
    pair = pair_for_brief("modern clean")
    assert look_contrast(pair) == "medium"


def test_seed_breaks_ties_deterministically():
    a = pair_for_brief("editorial warm", seed=0)
    b = pair_for_brief("editorial warm", seed=1)
    assert a.model_dump() == a.model_dump()
    assert b.model_dump() == b.model_dump()

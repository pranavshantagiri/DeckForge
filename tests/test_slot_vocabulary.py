"""Canonical slot vocabulary contract tests."""

from __future__ import annotations

import pytest

from deckforge_core.schemas.blueprints import ContentKind
from deckforge_core.schemas.slot_vocabulary import (
    SLOT_VOCABULARY,
    has_vocabulary,
    slots_for,
)

ALL_ARCHETYPES = [
    "title", "section-divider", "agenda", "statement", "big-number",
    "two-column-text", "image-left", "image-right", "full-bleed-image",
    "three-cards", "comparison", "timeline", "process-flow", "chart", "table",
    "team", "quote", "closing",
]


def test_every_known_archetype_has_vocabulary():
    for arch in ALL_ARCHETYPES:
        assert has_vocabulary(arch), arch
        assert slots_for(arch).names(), arch


def test_no_unknown_archetype_keyed():
    assert "gibberish" not in SLOT_VOCABULARY
    with pytest.raises(KeyError):
        slots_for("gibberish")


def test_required_slots_are_first_fill_targets():
    voc = slots_for("big-number")
    assert voc.required() == ["number", "caption"]


def test_kinds_are_from_content_kind():
    for arch, voc in SLOT_VOCABULARY.items():
        for entry in voc.entries:
            assert entry.kinds, arch
            for k in entry.kinds:
                assert isinstance(k, ContentKind)


def test_timeline_and_agenda_items_are_lists():
    assert ContentKind.LIST in slots_for("timeline").kinds_for("items")
    assert ContentKind.LIST in slots_for("agenda").kinds_for("items")


def test_card_slots_are_text_kind():
    kinds = slots_for("three-cards").kinds_for("card_1")
    assert kinds and ContentKind.TEXT in kinds

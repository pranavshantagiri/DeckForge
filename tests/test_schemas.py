"""Contract tests: schemas must validate and round-trip JSON losslessly."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from deckforge_core.schemas.archetypes import Archetype
from deckforge_core.schemas.blueprints import (
    AlternateArrangement,
    Blueprint,
    BlueprintLibrary,
    ContentKind,
    SlotDef,
    SlotRegion,
    TextLimits,
)
from deckforge_core.schemas.deck_plan import DeckPlan, SlidePlan, SlotValue
from deckforge_core.schemas.pack import FormatPack, PaletteColor, StyleProfile


def test_archetype_enum_is_stable():
    assert Archetype("title") == Archetype.TITLE
    assert Archetype("big-number").value == "big-number"
    assert len(set(Archetype)) == len([a.value for a in Archetype])


def test_pack_roundtrip(canonical_pack: FormatPack):
    raw = canonical_pack.model_dump(mode="json")
    again = FormatPack.model_validate(raw)
    assert again.name == canonical_pack.name
    assert again.style.palette.hex("accent1") == "#C4472F"
    assert again.archetype_list() == [
        Archetype.TITLE,
        Archetype.BIG_NUMBER,
        Archetype.TWO_COLUMN_TEXT,
        Archetype.THREE_CARDS,
    ]


def test_palette_requires_hex_color():
    with pytest.raises(ValidationError):
        PaletteColor(role="bg", hex="red")


def test_palette_needs_at_least_one():
    with pytest.raises(ValidationError):
        StyleProfile(
            palette=__import__(
                "deckforge_core.schemas.pack", fromlist=["ColorPalette"]
            ).ColorPalette(colors=[]),
            fonts=None,
            type_scale=None,
        )


def _blueprint() -> Blueprint:
    return Blueprint(
        id="big-number",
        archetype=Archetype.BIG_NUMBER,
        slots=[
            SlotDef(
                name="number",
                kinds=[ContentKind.NUMBER],
                region=SlotRegion(x=0.1, y=0.25, w=0.8, h=0.4),
                style="big-number",
                align="center",
                valign="middle",
            ),
            SlotDef(
                name="caption",
                kinds=[ContentKind.TEXT],
                region=SlotRegion(x=0.1, y=0.66, w=0.8, h=0.15),
                text_limits=TextLimits(max_chars=160, max_lines=3),
            ),
        ],
        default_order=["number", "caption"],
        max_words_total=60,
    )


def test_blueprint_library_resolve_default():
    lib = BlueprintLibrary([_blueprint()])
    bp, slots = lib.resolve("big-number", "16:9")
    assert bp.id == "big-number"
    assert [s.name for s in slots] == ["number", "caption"]


def test_blueprint_library_resolve_portrait_alternate():
    bp = _blueprint()
    bp.alternatives.append(
        AlternateArrangement(
            aspect_ratio="portrait",
            description="stack number above caption on tall pages",
            slots=[
                SlotDef(name="number", kinds=[ContentKind.NUMBER],
                        region=SlotRegion(x=0.1, y=0.2, w=0.8, h=0.3),
                        style="big-number", align="center", valign="middle"),
                SlotDef(name="caption", kinds=[ContentKind.TEXT],
                        region=SlotRegion(x=0.1, y=0.55, w=0.8, h=0.2)),
            ],
        )
    )
    lib = BlueprintLibrary([bp])
    _, slots = lib.resolve("big-number", "9:16")
    assert len(slots) == 2
    assert slots[0].region.y == pytest.approx(0.2)
    _, default_slots = lib.resolve("big-number", "16:9")
    assert default_slots[0].region.y == pytest.approx(0.25)


def test_deck_plan_roundtrip():
    plan = DeckPlan(
        title="Quarterly Results",
        aspect_ratio="16:9",
        pack="demo",
        slides=[
            SlidePlan(
                n=1,
                archetype="big-number",
                title="Churn fell 12%",
                slots={
                    "number": SlotValue(number="12%"),
                    "caption": SlotValue(text="after onboarding changes"),
                },
                speaker_notes="Walk through the onboarding revamp.",
            )
        ],
    )
    raw = json.loads(plan.model_dump_json())
    again = DeckPlan.model_validate(raw)
    assert again.slides[0].slots["number"].number == "12%"
    # planner must never emit geometry: ensure schema has no coords on SlidePlan
    assert "region" not in raw["slides"][0]
    assert again.word_count >= 6


def test_slot_value_validation():
    with pytest.raises(ValidationError):
        # out-of-field keys are rejected (slot names come from blueprints, not
        # arbitrary strings in the plan schema)
        DeckPlan(pack="p", slides=[SlidePlan(n=1, archetype="twocolumn", slots={"bogus": 1})]).model_dump()

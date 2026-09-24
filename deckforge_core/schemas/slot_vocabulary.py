"""Canonical slot vocabulary per archetype.

This is the ORCHESTRATOR-owned contract between the planner (D) and the
renderer (C):
- The planner fills exactly these slot names in ``SlidePlan.slots``.
- The renderer's blueprints map these names onto geometry; any slot name the
  blueprint does not recognise is ignored (with a QA warning).

Conventions for list-style content:
- ``items``: list of strings. For ``timeline`` each item is ``"YEAR|Title|detail"``
  and the renderer splits on the first ``|`` (``|detail`` optional). For
  ``agenda`` each item is plain text.
- Card slots (``card_1..card_3``): a ``SlotValue`` whose ``text`` is the card
  heading and whose ``paragraphs`` hold the body (at most 1 paragraph for v1).
- Comparison slots: ``left_heading``/``left_body``, ``right_heading``/``right_body``
  plus optional ``left_label``/``right_label`` kickers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from deckforge_core.schemas.archetypes import Archetype
from deckforge_core.schemas.blueprints import ContentKind


@dataclass(frozen=True)
class SlotVocEntry:
    name: str
    kinds: tuple[ContentKind, ...]
    required: bool = False
    label: str = ""
    note: str = ""


@dataclass(frozen=True)
class ArchetypeSlots:
    archetype: Archetype
    entries: tuple[SlotVocEntry, ...] = field(default_factory=tuple)

    def names(self) -> list[str]:
        return [e.name for e in self.entries]

    def required(self) -> list[str]:
        return [e.name for e in self.entries if e.required]

    def kinds_for(self, name: str) -> Optional[tuple[ContentKind, ...]]:
        for e in self.entries:
            if e.name == name:
                return e.kinds
        return None


T = ContentKind.TEXT
P = ContentKind.PARAGRAPHS
L = ContentKind.LIST
N = ContentKind.NUMBER
IM = ContentKind.IMAGE
C = ContentKind.CHART
TAB = ContentKind.TABLE
D = ContentKind.DIAGRAM
PE = ContentKind.PERSON

SLOT_VOCABULARY: dict[str, ArchetypeSlots] = {
    Archetype.TITLE.value: ArchetypeSlots(
        Archetype.TITLE,
        (
            SlotVocEntry("kicker", (T,), False, "Kicker"),
            SlotVocEntry("title", (T,), True, "Title"),
            SlotVocEntry("subtitle", (T,), False, "Subtitle"),
            SlotVocEntry("author", (T,), False, "Author / date / org"),
        ),
    ),
    Archetype.SECTION_DIVIDER.value: ArchetypeSlots(
        Archetype.SECTION_DIVIDER,
        (
            SlotVocEntry("kicker", (T,), False, "Kicker"),
            SlotVocEntry("title", (T,), True, "Section title"),
            SlotVocEntry("meta", (T,), False, "Section meta"),
        ),
    ),
    Archetype.AGENDA.value: ArchetypeSlots(
        Archetype.AGENDA,
        (
            SlotVocEntry("kicker", (T,), False, "Kicker"),
            SlotVocEntry("items", (L,), True, "Agenda items"),
        ),
    ),
    Archetype.STATEMENT.value: ArchetypeSlots(
        Archetype.STATEMENT,
        (
            SlotVocEntry("statement", (T, P), True, "The big takeaway"),
            SlotVocEntry("source", (T,), False, "Attribution / footnote"),
        ),
    ),
    Archetype.BIG_NUMBER.value: ArchetypeSlots(
        Archetype.BIG_NUMBER,
        (
            SlotVocEntry("number", (N, T), True, "The headline number"),
            SlotVocEntry("caption", (T,), True, "One-line caption"),
            SlotVocEntry("source", (T,), False, "Attribution / footnote"),
        ),
    ),
    Archetype.TWO_COLUMN_TEXT.value: ArchetypeSlots(
        Archetype.TWO_COLUMN_TEXT,
        (
            SlotVocEntry("kicker", (T,), False, "Kicker"),
            SlotVocEntry("col_a_heading", (T,), False, "Left column heading"),
            SlotVocEntry("col_a_body", (P,), False, "Left column body"),
            SlotVocEntry("col_b_heading", (T,), False, "Right column heading"),
            SlotVocEntry("col_b_body", (P,), False, "Right column body"),
        ),
    ),
    Archetype.IMAGE_LEFT.value: ArchetypeSlots(
        Archetype.IMAGE_LEFT,
        (
            SlotVocEntry("title", (T,), True, "Title over the text column"),
            SlotVocEntry("body", (P,), True, "Body text"),
            SlotVocEntry("image", (IM,), True, "Image (ImageReq)"),
            SlotVocEntry("source", (T,), False, "Image attribution"),
        ),
    ),
    Archetype.IMAGE_RIGHT.value: ArchetypeSlots(
        Archetype.IMAGE_RIGHT,
        (
            SlotVocEntry("title", (T,), True, "Title over the text column"),
            SlotVocEntry("body", (P,), True, "Body text"),
            SlotVocEntry("image", (IM,), True, "Image (ImageReq)"),
            SlotVocEntry("source", (T,), False, "Image attribution"),
        ),
    ),
    Archetype.FULL_BLEED_IMAGE.value: ArchetypeSlots(
        Archetype.FULL_BLEED_IMAGE,
        (
            SlotVocEntry("image", (IM,), True, "Background image (ImageReq)"),
            SlotVocEntry("title", (T,), False, "Overlay title"),
            SlotVocEntry("caption", (T,), False, "Overlay caption"),
        ),
    ),
    Archetype.THREE_CARDS.value: ArchetypeSlots(
        Archetype.THREE_CARDS,
        (
            SlotVocEntry("title", (T,), False, "Slide title"),
            SlotVocEntry("card_1", (T,), False, "Card 1 (text=heading, paragraphs=[body])", "heading|body"),
            SlotVocEntry("card_2", (T,), False, "Card 2", "heading|body"),
            SlotVocEntry("card_3", (T,), False, "Card 3", "heading|body"),
        ),
    ),
    Archetype.COMPARISON.value: ArchetypeSlots(
        Archetype.COMPARISON,
        (
            SlotVocEntry("title", (T,), False, "Slide title"),
            SlotVocEntry("left_label", (T,), False, "Left column label"),
            SlotVocEntry("right_label", (T,), False, "Right column label"),
            SlotVocEntry("left_heading", (T,), False, "Left column heading"),
            SlotVocEntry("right_heading", (T,), False, "Right column heading"),
            SlotVocEntry("left_body", (P,), False, "Left column body"),
            SlotVocEntry("right_body", (P,), False, "Right column body"),
        ),
    ),
    Archetype.TIMELINE.value: ArchetypeSlots(
        Archetype.TIMELINE,
        (
            SlotVocEntry("title", (T,), False, "Slide title"),
            SlotVocEntry("items", (L,), True, "Items as YEAR|Title|detail"),
        ),
    ),
    Archetype.PROCESS_FLOW.value: ArchetypeSlots(
        Archetype.PROCESS_FLOW,
        (
            SlotVocEntry("title", (T,), False, "Slide title"),
            SlotVocEntry("diagram", (D,), True, "Flow diagram (DiagramSpec)"),
            SlotVocEntry("caption", (T,), False, "Diagram caption"),
        ),
    ),
    Archetype.CHART.value: ArchetypeSlots(
        Archetype.CHART,
        (
            SlotVocEntry("title", (T,), False, "Slide title"),
            SlotVocEntry("chart", (C,), True, "Chart (ChartSpec)"),
            SlotVocEntry("source", (T,), False, "Data source footnote"),
        ),
    ),
    Archetype.TABLE.value: ArchetypeSlots(
        Archetype.TABLE,
        (
            SlotVocEntry("title", (T,), False, "Slide title"),
            SlotVocEntry("table", (TAB,), True, "Table (TableSpec)"),
            SlotVocEntry("source", (T,), False, "Data source footnote"),
        ),
    ),
    Archetype.TEAM.value: ArchetypeSlots(
        Archetype.TEAM,
        (
            SlotVocEntry("title", (T,), False, "Slide title"),
            SlotVocEntry("people", (PE,), True, "People (list[PersonSpec])"),
        ),
    ),
    Archetype.QUOTE.value: ArchetypeSlots(
        Archetype.QUOTE,
        (
            SlotVocEntry("quote", (T, P), True, "The quote"),
            SlotVocEntry("attribution", (T,), False, "Who said it"),
        ),
    ),
    Archetype.CLOSING.value: ArchetypeSlots(
        Archetype.CLOSING,
        (
            SlotVocEntry("kicker", (T,), False, "Kicker"),
            SlotVocEntry("title", (T,), True, "Closing line / CTA"),
            SlotVocEntry("contact", (P,), False, "Contact lines"),
            SlotVocEntry("thanks", (T,), False, "Thank-you line"),
        ),
    ),
}


def slots_for(archetype: str | Archetype) -> ArchetypeSlots:
    key = archetype.value if isinstance(archetype, Archetype) else archetype
    voc = SLOT_VOCABULARY.get(key)
    if voc is None:
        raise KeyError(f"no canonical slot vocabulary for {key!r}")
    return voc


def has_vocabulary(archetype: str | Archetype) -> bool:
    key = archetype.value if isinstance(archetype, Archetype) else archetype
    return key in SLOT_VOCABULARY


def all_entries() -> list[ArchetypeSlots]:
    return list(SLOT_VOCABULARY.values())

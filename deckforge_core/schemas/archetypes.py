"""Slide archetypes: the shared vocabulary of slides both the analysis and the
planner speak in. Extensible; unknown archetypes discovered during ingestion
are recorded as new enum values on a pack's blueprint set, never invented
ad-hoc by the planner."""

from __future__ import annotations

import enum


class Archetype(str, enum.Enum):
    TITLE = "title"
    SECTION_DIVIDER = "section-divider"
    AGENDA = "agenda"
    STATEMENT = "statement"
    BIG_NUMBER = "big-number"
    TWO_COLUMN_TEXT = "two-column-text"
    IMAGE_LEFT = "image-left"
    IMAGE_RIGHT = "image-right"
    FULL_BLEED_IMAGE = "full-bleed-image"
    THREE_CARDS = "three-cards"
    COMPARISON = "comparison"
    TIMELINE = "timeline"
    PROCESS_FLOW = "process-flow"
    CHART = "chart"
    TABLE = "table"
    TEAM = "team"
    QUOTE = "quote"
    CLOSING = "closing"


ARCHETYPE_ORDER: tuple[str, ...] = tuple(a.value for a in Archetype)

# Human-friendly labels for the CLI/GUI and the planner prompt.
ARCHETYPE_LABELS: dict[str, str] = {
    "title": "Title",
    "section-divider": "Section divider",
    "agenda": "Agenda / contents",
    "statement": "Statement / big takeaway",
    "big-number": "Big number / KPI",
    "two-column-text": "Two columns of text",
    "image-left": "Image on the left, text on the right",
    "image-right": "Image on the right, text on the left",
    "full-bleed-image": "Full-bleed image with caption",
    "three-cards": "Three cards",
    "comparison": "Comparison / pros vs cons",
    "timeline": "Timeline",
    "process-flow": "Process / flow",
    "chart": "Chart with data",
    "table": "Table",
    "team": "Team / people",
    "quote": "Pull quote",
    "closing": "Closing / contact",
}

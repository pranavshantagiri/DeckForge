"""Deck Plan: what the LLM/planner outputs and the renderer consumes.

The planner NEVER emits coordinates, colours, fonts or sizes. Those come only
from the pack (its StyleProfile + Blueprints). Slots are keyed by the
blueprint's slot names; the renderer maps them onto geometry.
"""

from __future__ import annotations

from typing import Optional, Union

from pydantic import BaseModel, Field

from deckforge_core.schemas.archetypes import Archetype


# --------------------------------------------------------------------------- #
# Content specs that can live inside a slot value
# --------------------------------------------------------------------------- #
class ChartSeries(BaseModel):
    name: str
    values: list[float] = Field(default_factory=list)
    color_role: Optional[str] = None  # palette role; None = pack default


class ChartSpec(BaseModel):
    chart_type: str = "column"  # column | bar | line | area | pie | donut
    categories: list[str] = Field(default_factory=list)
    series: list[ChartSeries] = Field(default_factory=list)
    units: Optional[str] = None
    data_labels: bool = False
    show_legend: bool = True


class TableSpec(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    header_row: bool = True
    col_widths: Optional[list[float]] = None  # relative, sums to 1
    zebra_rows: bool = True


class GraphNode(BaseModel):
    id: str
    label: str = ""
    kind: str = "process"  # process | decision | start | end | note | data
    x: Optional[float] = None  # optional absolute relative coords (0..1)
    y: Optional[float] = None


class GraphEdge(BaseModel):
    src: str
    dst: str
    label: Optional[str] = None
    style: Optional[str] = None  # e.g. "elbow" | "straight"


class GraphSpec(BaseModel):
    directed: bool = True
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class DiagramSpec(BaseModel):
    """Either an explicit graph spec or a Mermaid source string."""

    graph: Optional[GraphSpec] = None
    mermaid: Optional[str] = None
    caption: Optional[str] = None


class PersonSpec(BaseModel):
    name: str
    role: str = ""
    image_query: Optional[str] = None
    image_url: Optional[str] = None


class ImageReq(BaseModel):
    query: Optional[str] = None
    provider: Optional[str] = None
    url: Optional[str] = None
    alt: Optional[str] = None
    attribution: Optional[str] = None


# --------------------------------------------------------------------------- #
# Slot value
# --------------------------------------------------------------------------- #
class SlotValue(BaseModel):
    """Flexible content for one named slot. The renderer checks each slot's
    allowed ContentKinds against whatever is populated here."""

    text: Optional[str] = None
    paragraphs: Optional[list[str]] = None
    items: Optional[list[str]] = None  # bullets / list items
    number: Optional[Union[float, str]] = None
    chart: Optional[ChartSpec] = None
    table: Optional[TableSpec] = None
    diagram: Optional[DiagramSpec] = None
    people: Optional[list[PersonSpec]] = None
    image: Optional[ImageReq] = None
    source: Optional[str] = None  # attribution / footer line
    url: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return not any(
            [
                self.text,
                self.paragraphs,
                self.items,
                self.number is not None,
                self.chart,
                self.table,
                self.diagram,
                self.people,
                self.image,
                self.source,
            ]
        )


# --------------------------------------------------------------------------- #
# Slide + deck plans
# --------------------------------------------------------------------------- #
class SlidePlan(BaseModel):
    n: int = Field(ge=1)
    archetype: str  # Archetype value; stored as str so unknown discovered ones survive
    title: Optional[str] = None  # takeaway-style title when the blueprint has one
    slots: dict[str, SlotValue] = Field(default_factory=dict)
    image_query: Optional[str] = None  # convenience: front-page image for full-bleed
    speaker_notes: Optional[str] = None
    section: Optional[str] = None

    @property
    def archetype_enum(self) -> Archetype:
        try:
            return Archetype(self.archetype)
        except ValueError:
            return Archetype.TWO_COLUMN_TEXT


class DeckPlan(BaseModel):
    title: str = "Untitled Deck"
    subtitle: Optional[str] = None
    audience: Optional[str] = None
    aspect_ratio: str = "16:9"
    pack: str
    slides: list[SlidePlan] = Field(default_factory=list)
    created_by: str = ""  # provider/model identifier
    created_at: Optional[str] = None

    @property
    def word_count(self) -> int:
        import re

        total = 0
        for s in self.slides:
            for v in s.slots.values():
                for chunk in (v.text, v.source, s.title):
                    if chunk:
                        total += len(re.findall(r"\S+", chunk))
                if v.paragraphs:
                    total += sum(len(re.findall(r"\S+", p)) for p in v.paragraphs)
                if v.items:
                    total += sum(len(re.findall(r"\S+", i)) for i in v.items)
        return total

    def archetype_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in self.slides:
            counts[s.archetype] = counts.get(s.archetype, 0) + 1
        return counts

"""Blueprints: one file per slide archetype describing slot geometry.

All geometry is in RELATIVE units (fractions of slide width/height, 0..1) so a
blueprint can be rescaled to any aspect ratio. Min/max text lengths come from
real usage during analysis. Aspect-ratio alternates declare rearrangements for
ratios where the default arrangement would squash.
"""

from __future__ import annotations

import enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from deckforge_core.schemas.archetypes import Archetype


class ContentKind(str, enum.Enum):
    TEXT = "text"  # single short string (title, kicker, label)
    PARAGRAPHS = "paragraphs"  # body copy, several lines
    LIST = "list"  # bullet / numbered list
    NUMBER = "number"  # headline statistic
    IMAGE = "image"
    CHART = "chart"
    TABLE = "table"
    DIAGRAM = "diagram"
    PERSON = "person"  # people card (name, role, maybe portrait)
    ICON = "icon"
    NOTES = "notes"  # speaker notes only, not visible


class SlotRegion(BaseModel):
    """Relative geometry. ``x``/``w`` are fractions of slide width,
    ``y``/``h`` fractions of slide height. All values in [0, 1]."""

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def _fits(self) -> "SlotRegion":
        if self.x + self.w > 1.0 + 1e-6 or self.y + self.h > 1.0 + 1e-6:
            raise ValueError("slot region must stay inside the slide")
        return self


class TextLimits(BaseModel):
    min_chars: int = Field(default=0, ge=0)
    max_chars: int = Field(default=100_000)
    max_lines: int = Field(default=8, ge=1)
    min_words: int = Field(default=0, ge=0)
    max_words: int = Field(default=100_000)


class SlotDef(BaseModel):
    """A named content region on a slide. ``style`` references an entry in
    ``StyleProfile.type_scale`` ("h1", "body", "big-number", ...)."""

    name: str
    label: str = ""  # human label, e.g. "Heading"
    kinds: list[ContentKind] = Field(default_factory=lambda: [ContentKind.TEXT])
    region: SlotRegion
    align: str = "left"  # left | center | right | justify
    valign: str = "top"  # top | middle | bottom
    style: str = "body"  # type-scale entry name
    text_limits: Optional[TextLimits] = None
    optional: bool = False
    image_fit: str = "crop"  # crop | fit
    wrap: bool = True

    def accepts(self, kind: ContentKind) -> bool:
        return kind in self.kinds


class AlternateArrangement(BaseModel):
    """A re-layout of a whole slide for a target aspect ratio."""

    aspect_ratio: str  # e.g. "4:3" or "portrait"
    description: str
    slots: list[SlotDef] = Field(default_factory=list)


class Blueprint(BaseModel):
    """Defines how to render one archetype. ``slots`` are the default layout;
    ``alternatives`` provide per-archetype rearrangements for extreme ratios."""

    id: str  # == archetype value
    archetype: Archetype
    label: str = ""
    description: str = ""
    slots: list[SlotDef] = Field(default_factory=list)
    default_order: list[str] = Field(default_factory=list)  # suggested fill order
    alternatives: list[AlternateArrangement] = Field(default_factory=list)
    min_words_total: int = Field(default=0, ge=0)
    max_words_total: int = Field(default=100_000)
    example_ref: Optional[str] = None  # relative path to example slide / thumb
    example_thumbnail: Optional[str] = None

    def slot(self, name: str) -> SlotDef:
        for s in self.slots:
            if s.name == name:
                return s
        raise KeyError(name)

    def has_slot(self, name: str) -> bool:
        return any(s.name == name for s in self.slots)

    def fill_order(self) -> list[str]:
        names = [s.name for s in self.slots]
        return [n for n in self.default_order if n in names] + [
            n for n in names if n not in self.default_order
        ]


class BlueprintLibrary:
    """A collection of blueprints for one pack, mirroring ``blueprints/`` dir."""

    def __init__(self, blueprints: list[Blueprint]) -> None:
        self._by_id: dict[str, Blueprint] = {b.id: b for b in blueprints}

    @classmethod
    def empty(cls) -> "BlueprintLibrary":
        return cls([])

    def add(self, blueprint: Blueprint) -> None:
        self._by_id[blueprint.id] = blueprint

    def get(self, archetype: str | Archetype) -> Optional[Blueprint]:
        key = archetype.value if isinstance(archetype, Archetype) else archetype
        return self._by_id.get(key)

    def require(self, archetype: str | Archetype) -> Blueprint:
        b = self.get(archetype)
        if b is None:
            raise KeyError(f"no blueprint for archetype {archetype!r}")
        return b

    def resolve(
        self, archetype: str | Archetype, aspect_ratio: str
    ) -> tuple[Blueprint, list[SlotDef]]:
        """Return (blueprint, effective slot layout) for an aspect ratio.

        Uses the blueprint's declared alternate arrangement when one matches
        ``aspect_ratio`` (or its dominant dimension: "portrait"), else the
        default layout.
        """
        b = self.require(archetype)
        for alt in b.alternatives:
            if _matches(alt.aspect_ratio, aspect_ratio) and alt.slots:
                return b, alt.slots
        return b, b.slots

    def all(self) -> list[Blueprint]:
        return list(self._by_id.values())

    def archetypes(self) -> list[str]:
        return [b.id for b in self.all()]

    def __iter__(self):
        return iter(self.all())


def _matches(pattern: str, ratio: str) -> bool:
    """True when a blueprint arrangement's aspect-ratio pattern matches ``ratio``."""
    pat = pattern.strip().lower()
    r = ratio.strip().lower()
    if pat == r:
        return True
    try:
        pnum, pden = pat.split(":")
        rnum, rden = r.split(":")
        if float(pnum) == 0 or float(rnum) == 0:
            return False
        return abs(float(pnum) / float(pden) - float(rnum) / float(rden)) < 0.05
    except (ValueError, IndexError):
        if pat in ("portrait", "vertical"):
            return _is_portrait(ratio)
        if pat in ("landscape",):
            return not _is_portrait(ratio)
        return False


def _is_portrait(ratio: str) -> bool:
    try:
        n, d = ratio.split(":")
        return float(n) / float(d) < 1.0
    except (ValueError, IndexError):
        return False

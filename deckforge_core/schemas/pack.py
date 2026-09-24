"""Format Pack and its Style Profile (pack.json + style_profile.json).

The Style Profile is the distilled, statistical "look" of a collection of decks:
palette *with roles*, font pair, type scale, margins/grid, spacing, image
treatment, and density statistics. The renderer consumes ONLY this profile for
geometry and styling; the planner never outputs colours or coordinates.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from deckforge_core.schemas.archetypes import Archetype


# --------------------------------------------------------------------------- #
# Palette
# --------------------------------------------------------------------------- #
class PaletteRole(str, enum.Enum):
    BG = "bg"
    TEXT = "text"
    MUTED_TEXT = "muted-text"
    ACCENT1 = "accent1"
    ACCENT2 = "accent2"
    ACCENT3 = "accent3"
    NEUTRAL1 = "neutral1"
    NEUTRAL2 = "neutral2"
    CARD_BG = "card-bg"
    LINE = "line"


class PaletteColor(BaseModel):
    role: str
    hex: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    usage_pct: float = Field(default=0.0, ge=0.0, le=100.0)


class ColorPalette(BaseModel):
    """Ordered palette. ``colors[0]`` is the dominant role by convention."""

    colors: list[PaletteColor] = Field(default_factory=list)

    @field_validator("colors")
    @classmethod
    def _at_least_one(cls, v: list[PaletteColor]) -> list[PaletteColor]:
        if not v:
            raise ValueError("palette must have at least one colour")
        return v

    def hex(self, role: str) -> str:
        for c in self.colors:
            if c.role == role:
                return c.hex
        raise KeyError(role)

    def has(self, role: str) -> bool:
        return any(c.role == role for c in self.colors)

    def dominant(self) -> str:
        return max(self.colors, key=lambda c: c.usage_pct).hex


# --------------------------------------------------------------------------- #
# Fonts + type scale
# --------------------------------------------------------------------------- #
class FontPair(BaseModel):
    heading: str
    body: str
    fallback: list[str] = Field(default_factory=list)
    heading_usage_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    body_usage_pct: float = Field(default=0.0, ge=0.0, le=100.0)


class TypeScaleEntry(BaseModel):
    name: str  # h1, h2, kicker, body, small, big-number, caption
    size_pt: float = Field(gt=0)
    weight: str = "regular"  # regular | medium | bold
    caps: str = "none"  # none | sentence | title | upper
    line_spacing: float = Field(default=1.1, gt=0)
    tracking_pt: float = Field(default=0.0)
    space_after_pt: float = Field(default=0.0)


class TypeScale(BaseModel):
    entries: list[TypeScaleEntry] = Field(default_factory=list)

    def entry(self, name: str) -> TypeScaleEntry:
        for e in self.entries:
            if e.name == name:
                return e
        raise KeyError(name)


# --------------------------------------------------------------------------- #
# Grid + spacing
# --------------------------------------------------------------------------- #
class Margins(BaseModel):
    left: float = Field(default=0.06, ge=0.0, lt=0.5)
    right: float = Field(default=0.06, ge=0.0, lt=0.5)
    top: float = Field(default=0.06, ge=0.0, lt=0.5)
    bottom: float = Field(default=0.06, ge=0.0, lt=0.5)


class Grid(BaseModel):
    columns: int = Field(default=12, ge=1, le=48)
    gutter: float = Field(default=0.02, ge=0.0, lt=0.2)  # relative to width
    baseline_step: float = Field(default=0.02, gt=0.0, lt=0.5)  # rel to height


class ImageTreatment(BaseModel):
    mode: str = "framed"  # full-bleed | framed | rounded | none
    corner_radius: float = Field(default=0.0, ge=0.0, lt=0.5)
    frame_color: Optional[str] = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    frame_weight_pt: float = Field(default=0.0, ge=0.0)


# --------------------------------------------------------------------------- #
# Density + confidence
# --------------------------------------------------------------------------- #
class DensityStats(BaseModel):
    words_per_slide_median: int = 0
    words_per_slide_max: int = 0
    bullets_per_slide_median: int = 0
    image_area_fraction_median: float = 0.0
    mean_shapes_per_slide: float = 0.0
    slides_analysed: int = 0


class StyleConfidence(BaseModel):
    overall: float = Field(default=0.0, ge=0.0, le=1.0)
    palette: float = Field(default=0.0, ge=0.0, le=1.0)
    fonts: float = Field(default=0.0, ge=0.0, le=1.0)
    grid: float = Field(default=0.0, ge=0.0, le=1.0)
    layout: float = Field(default=0.0, ge=0.0, le=1.0)


# --------------------------------------------------------------------------- #
# StyleProfile + FormatPack
# --------------------------------------------------------------------------- #
class StyleProfile(BaseModel):
    version: int = 1
    palette: ColorPalette
    fonts: FontPair
    type_scale: TypeScale
    margins: Margins = Field(default_factory=Margins)
    grid: Grid = Field(default_factory=Grid)
    corner_radii: float = Field(default=0.0, ge=0.0, lt=0.5)
    line_weight_pt: float = Field(default=1.0, ge=0.0)
    image_treatment: ImageTreatment = Field(default_factory=ImageTreatment)
    density: DensityStats = Field(default_factory=DensityStats)
    confidence: StyleConfidence = Field(default_factory=StyleConfidence)
    notes: list[str] = Field(default_factory=list)


PACK_SCHEMA_VERSION = 1
STYLE_SCHEMA_VERSION = 1


class FormatPack(BaseModel):
    """Metadata for a Format Pack (pack.json). Style profile and blueprints
    live as sibling files, not inside this model."""

    format_version: int = PACK_SCHEMA_VERSION
    name: str
    version: str = "1.0"
    source_deck_count: int = Field(default=0, ge=0)
    source_slide_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    aspect_ratios: list[str] = Field(default_factory=lambda: ["16:9"])
    archetypes: list[str] = Field(default_factory=list)
    default_archetype_order: list[str] = Field(default_factory=list)
    style: StyleProfile

    def archetype_list(self) -> list[Archetype]:
        out: list[Archetype] = []
        for a in self.archetypes:
            try:
                out.append(Archetype(a))
            except ValueError:
                continue
        return out

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

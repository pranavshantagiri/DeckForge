"""Extraction output contract (Workstream A: Ingest & Parse).

These models describe a deck *as extracted* from a real/synthetic .pptx file:
geometry normalised to RELATIVE fractions of slide width/height (0..1), text
split into runs/paragraphs, plus charts, tables, connectors, notes and images.

Contracts live in ``deckforge_core.schemas`` (see ``__init__``). Analysis
(Workstream B) consumes these models to distil a :class:`StyleProfile` and
per-archetype :class:`Blueprint`.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

EMU_PER_INCH = 914400  # 1 inch == 914400 EMU
EMU_PER_PT = 12700  # 1 pt == 12700 EMU

# Known slide sizes (EMU) used as ratio references when reducing aspect ratio.
_STANDARD_RATIOS: tuple[tuple[str, float], ...] = (
    ("16:9", 16.0 / 9.0),
    ("16:10", 16.0 / 10.0),
    ("4:3", 4.0 / 3.0),
    ("3:2", 3.0 / 2.0),
    ("1:1", 1.0),
)
_RATIO_TOLERANCE = 0.02


def aspect_ratio(width_emu: int, height_emu: int) -> str:
    """Return a human ratio string like ``"16:9"``, ``"4:3"`` or ``"portrait"``.

    Portrait decks (height > width) are labelled ``"portrait"``; unusual
    landscape ratios fall back to ``"landscape"``.
    """
    if width_emu <= 0 or height_emu <= 0:
        return ""
    if height_emu > width_emu:
        return "portrait"
    value = float(width_emu) / float(height_emu)
    for label, ratio in _STANDARD_RATIOS:
        if abs(value - ratio) / ratio < _RATIO_TOLERANCE:
            return label
    return "landscape"


class ExtractedTextRun(BaseModel):
    """One styled run of text inside a paragraph."""

    text: str = ""
    font_name: Optional[str] = None
    size_pt: Optional[float] = None
    bold: bool = False
    italic: bool = False
    color_hex: Optional[str] = None  # "#RRGGBB" when an explicit fill is set


class ExtractedParagraph(BaseModel):
    """A paragraph: a sequence of runs plus its alignment ("left|center|right|justify")."""

    runs: list[ExtractedTextRun] = Field(default_factory=list)
    alignment: Optional[str] = None

    def text(self) -> str:
        return "".join(r.text for r in self.runs)

    def word_count(self) -> int:
        return len(self.text().split())


class ExtractedImageRef(BaseModel):
    """Reference to an embedded raster image on a shape."""

    embedded_part_name: str = ""  # e.g. "image5.png"
    width_px: int = 0
    height_px: int = 0
    sha256: str = ""  # sha256 of the exact embedded bytes
    mime: str = ""  # e.g. "image/png"


class ExtractedChartSeries(BaseModel):
    name: str
    values: list[float] = Field(default_factory=list)


class ExtractedChart(BaseModel):
    chart_type: str = ""  # e.g. "COLUMN_CLUSTERED"
    categories: list[str] = Field(default_factory=list)
    series: list[ExtractedChartSeries] = Field(default_factory=list)


class ExtractedTable(BaseModel):
    rows: list[list[str]] = Field(default_factory=list)
    header_row_count: int = 0
    col_count: int = 0


class ExtractedConnector(BaseModel):
    begin_shape_id: Optional[int] = None
    end_shape_id: Optional[int] = None
    line_hex: Optional[str] = None
    weight_pt: Optional[float] = None


class ExtractedShape(BaseModel):
    """One shape (or grouped sub-shape) on a slide.

    Geometry (``x``/``y``/``w``/``h``) is stored as RELATIVE fractions of the
    slide width/height, i.e. 0..1, bounded by the slide *including* the normal
    case of shapes bleeding off the edge (raw values are preserved, not
    clamped, so analysis can distinguish full-bleed from clipped decorations).
    """

    shape_id: int = 0
    name: str = ""
    shape_type: str = ""  # MSO shape type name, e.g. "TEXT_BOX", "PICTURE"
    is_placeholder: bool = False
    placeholder_type: Optional[str] = None  # e.g. "CENTER_TITLE", "SUBTITLE"
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    rotation_deg: float = 0.0
    fill_hex: Optional[str] = None
    line_hex: Optional[str] = None
    text: list[ExtractedParagraph] = Field(default_factory=list)
    image: Optional[ExtractedImageRef] = None

    def has_text(self) -> bool:
        return any(p.text().strip() for p in self.text)

    def text_joined(self) -> str:
        return "".join(p.text() for p in self.text)

    def word_count(self) -> int:
        return len(self.text_joined().split())


class ExtractedSlide(BaseModel):
    index: int = Field(ge=1)  # 1-based
    slide_size_emu: tuple[int, int] = (0, 0)  # (width, height)
    aspect_ratio: str = "16:9"
    shapes: list[ExtractedShape] = Field(default_factory=list)
    charts: list[ExtractedChart] = Field(default_factory=list)
    tables: list[ExtractedTable] = Field(default_factory=list)
    connectors: list[ExtractedConnector] = Field(default_factory=list)
    notes_text: Optional[str] = None
    layout_name: str = ""
    has_image_slides_whole_thing: bool = False  # one picture covers the slide
    extraction_errors: list[str] = Field(default_factory=list)

    @property
    def word_count(self) -> int:
        return total_words(self)


class ExtractedDeck(BaseModel):
    path: str = ""
    slide_count: int = 0
    size_emu: tuple[int, int] = (0, 0)  # (width, height) of the deck
    slides: list[ExtractedSlide] = Field(default_factory=list)

    @property
    def aspect_ratio(self) -> str:
        return aspect_ratio(*self.size_emu)


class ExtractedDeckRecord(BaseModel):
    """Cache record: file hash plus the extracted deck it parsed to."""

    hash: str
    deck: ExtractedDeck


class SlideGeometry:
    """Conversions between EMU absolute geometry and relative (0..1) units.

    ``to_rel`` divides EMU values by the slide dimensions so every shape can be
    compared across decks of different sizes/aspect ratios.
    """

    def __init__(self, slide_width_emu: int, slide_height_emu: int) -> None:
        if not slide_width_emu or not slide_height_emu:
            raise ValueError("slide dimensions must be non-zero")
        self.slide_width_emu = float(int(slide_width_emu))
        self.slide_height_emu = float(int(slide_height_emu))

    def to_rel(
        self, emu_x: int, emu_y: int, emu_w: int, emu_h: int
    ) -> tuple[float, float, float, float]:
        """Convert an EMU bounding box to relative (x, y, w, h) fractions."""
        x = float(emu_x) / self.slide_width_emu
        y = float(emu_y) / self.slide_height_emu
        w = float(emu_w) / self.slide_width_emu
        h = float(emu_h) / self.slide_height_emu
        return x, y, w, h

    @staticmethod
    def emu_to_inches(emu: int) -> float:
        return float(emu) / EMU_PER_INCH

    @staticmethod
    def inches_to_emu(inches: float) -> int:
        return int(round(float(inches) * EMU_PER_INCH))

    @staticmethod
    def emu_to_pt(emu: int) -> float:
        return float(emu) / EMU_PER_PT

    @staticmethod
    def pt_to_emu(pt: float) -> int:
        return int(round(float(pt) * EMU_PER_PT))

    @staticmethod
    def inches_to_pt(inches: float) -> float:
        return float(inches) * 72.0

    @staticmethod
    def pt_to_inches(pt: float) -> float:
        return float(pt) / 72.0


# --------------------------------------------------------------------------- #
# Aggregation helpers (used by analysis later for density statistics)
# --------------------------------------------------------------------------- #
def shape_text(shape: ExtractedShape) -> str:
    return shape.text_joined()


def slide_text(slide: ExtractedSlide) -> str:
    """All visible text on the slide (shapes only; notes excluded)."""
    return "".join(shape_text(s) for s in slide.shapes)


def total_words(slide: ExtractedSlide) -> int:
    """Word count across all visible shape text on the slide."""
    return len(slide_text(slide).split())


def total_words_in_deck(deck: ExtractedDeck) -> int:
    return sum(total_words(s) for s in deck.slides)


def text_area_fraction(slide: ExtractedSlide) -> float:
    """Fraction of slide area covered by shapes that carry text."""
    total = 0.0
    for s in slide.shapes:
        if s.has_text():
            total += s.w * s.h
    return min(total, 1.0)


def image_area_fraction(slide: ExtractedSlide) -> float:
    """Fraction of slide area covered by picture shapes."""
    total = 0.0
    for s in slide.shapes:
        if s.image is not None:
            total += s.w * s.h
    return min(total, 1.0)


def text_density(slide: ExtractedSlide) -> float:
    """Words per unit of text-covered relative area (density heuristic)."""
    area = text_area_fraction(slide)
    if area <= 1e-6:
        return 0.0
    return total_words(slide) / area

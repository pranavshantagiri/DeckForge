"""Workstream A: parse .pptx decks into :class:`ExtractedDeck` records.

Never crashes on weird files: per-shape extraction is guarded, per-slide
errors are recorded into ``ExtractedSlide.extraction_errors``, and unopenable
files (junk bytes, password-protected CFB/OA containers) surface as
:class:`InvalidDeckError` so :func:`extract_directory` records them instead of
exploding.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from pptx import Presentation
from pptx.enum.dml import MSO_FILL
from pptx.enum.shapes import MSO_SHAPE_TYPE

from deckforge_core.errors import InvalidDeckError
from deckforge_core.ingest.cache import IngestCache, deck_hash
from deckforge_core.logging_util import get_logger
from deckforge_core.schemas.extracted import (
    EMU_PER_PT,
    ExtractedChart,
    ExtractedChartSeries,
    ExtractedConnector,
    ExtractedDeck,
    ExtractedImageRef,
    ExtractedParagraph,
    ExtractedShape,
    ExtractedSlide,
    ExtractedTable,
    ExtractedTextRun,
    SlideGeometry,
    aspect_ratio,
)

log = get_logger("deckforge.ingest.parser")


# --------------------------------------------------------------------------- #
# Result containers
# --------------------------------------------------------------------------- #
@dataclass
class IngestError:
    path: Path
    message: str


@dataclass
class IngestResult:
    """Outcome of walking a directory of .pptx files."""

    decks: list[ExtractedDeck] = field(default_factory=list)
    errors: list[IngestError] = field(default_factory=list)
    cached_hits: int = 0
    new_parses: int = 0


# --------------------------------------------------------------------------- #
# Small extraction primitives
# --------------------------------------------------------------------------- #
def _rgb_to_hex(rgb) -> str:
    return f"#{int(rgb):06X}"


def _fill_hex(shape) -> Optional[str]:
    try:
        fill = shape.fill
        if fill is not None and fill.type == MSO_FILL.SOLID:
            return _rgb_to_hex(fill.fore_color.rgb)
    except Exception:
        pass
    return None


def _line_hex(shape) -> Optional[str]:
    try:
        line = shape.line
        if line is not None and line.fill.type == MSO_FILL.SOLID:
            return _rgb_to_hex(line.color.rgb)
    except Exception:
        pass
    return None


def _line_weight_pt(shape) -> Optional[float]:
    try:
        width = shape.line.width
        if width is None:
            return None
        return float(width) / EMU_PER_PT
    except Exception:
        return None


def _run_color(font) -> Optional[str]:
    try:
        return _rgb_to_hex(font.color.rgb)
    except Exception:
        return None


def _alignment_name(alignment) -> Optional[str]:
    if alignment is None:
        return None
    name = getattr(alignment, "name", None)
    if name:
        return name.lower()
    return str(alignment).split("(")[0].strip().lower() or None


def _paragraphs_for(shape) -> list[ExtractedParagraph]:
    """Read a shape's text frame into paragraph models. Non-text shapes yield []."""
    if not getattr(shape, "has_text_frame", False) or not shape.has_text_frame:
        return []
    try:
        text_frame = shape.text_frame
    except Exception:
        return []
    paras: list[ExtractedParagraph] = []
    for p in getattr(text_frame, "paragraphs", ()) or ():
        runs: list[ExtractedTextRun] = []
        for r in getattr(p, "runs", ()) or ():
            try:
                size_pt = r.font.size.pt if r.font.size is not None else None
            except Exception:
                size_pt = None
            runs.append(
                ExtractedTextRun(
                    text=r.text or "",
                    font_name=r.font.name,
                    size_pt=size_pt,
                    bold=bool(r.font.bold),
                    italic=bool(r.font.italic),
                    color_hex=_run_color(r.font),
                )
            )
        paras.append(ExtractedParagraph(runs=runs, alignment=_alignment_name(p.alignment)))
    return paras


def _image_for(shape) -> Optional[ExtractedImageRef]:
    if getattr(shape, "shape_type", None) != MSO_SHAPE_TYPE.PICTURE:
        return None
    try:
        image = shape.image
        blob = image.blob
        width, height = image.size
        return ExtractedImageRef(
            embedded_part_name=image.filename,
            width_px=int(width),
            height_px=int(height),
            sha256=hashlib.sha256(blob).hexdigest(),
            mime=image.content_type,
        )
    except Exception:
        return None


def _shape_type_name(shape) -> str:
    try:
        st = shape.shape_type
        if st is None:
            return ""
        return getattr(st, "name", "") or str(st).split("(")[0].strip()
    except Exception:
        return ""


def _placeholder_type(shape) -> Optional[str]:
    if not getattr(shape, "is_placeholder", False):
        return None
    try:
        pf = shape.placeholder_format
        pt = pf.type if pf is not None else None
        if pt is None:
            return None
        return (getattr(pt, "name", None) or str(pt).split("(")[0].strip()) or None
    except Exception:
        return None


def _extract_shape(shape, geometry: SlideGeometry) -> Optional[ExtractedShape]:
    """Extract one non-line shape. Returns None and logs nothing; callers
    catch exceptions around this for per-shape resilience."""
    left = getattr(shape, "left", None) or 0
    top = getattr(shape, "top", None) or 0
    width = getattr(shape, "width", None) or 0
    height = getattr(shape, "height", None) or 0
    x, y, w, h = geometry.to_rel(int(left), int(top), int(width), int(height))
    rotation = 0.0
    try:
        rotation = float(getattr(shape, "rotation", 0.0) or 0.0)
    except Exception:
        pass
    return ExtractedShape(
        shape_id=int(getattr(shape, "shape_id", 0) or 0),
        name=str(getattr(shape, "name", "") or ""),
        shape_type=_shape_type_name(shape),
        is_placeholder=bool(getattr(shape, "is_placeholder", False)),
        placeholder_type=_placeholder_type(shape),
        x=x,
        y=y,
        w=w,
        h=h,
        rotation_deg=rotation,
        fill_hex=_fill_hex(shape),
        line_hex=_line_hex(shape),
        text=_paragraphs_for(shape),
        image=_image_for(shape),
    )


def _conn_shape_id(conn) -> Optional[int]:
    try:
        if conn is None:
            return None
        cs = conn()
        if cs is None:
            return None
        return int(cs.shape.shape_id)
    except Exception:
        return None


def _extract_connector(shape) -> ExtractedConnector:
    begin, end = None, None
    try:
        begin = _conn_shape_id(shape.begin_connect)
        end = _conn_shape_id(shape.end_connect)
    except Exception:
        pass
    return ExtractedConnector(
        begin_shape_id=begin,
        end_shape_id=end,
        line_hex=_line_hex(shape),
        weight_pt=_line_weight_pt(shape),
    )


def _extract_chart(shape) -> Optional[ExtractedChart]:
    try:
        chart = shape.chart
        chart_type = ""
        try:
            chart_type = getattr(chart.chart_type, "name", "") or str(chart.chart_type)
        except Exception:
            pass
        categories: list[str] = []
        try:
            if chart.plots:
                plot = chart.plots[0]
                categories = [str(c) for c in plot.categories]
        except Exception:
            pass
        series: list[ExtractedChartSeries] = []
        for s in chart.series:
            try:
                values = [float(v) for v in s.values]
            except Exception:
                values = []
            series.append(ExtractedChartSeries(name=str(s.name), values=values))
        return ExtractedChart(
            chart_type=chart_type, categories=categories, series=series
        )
    except Exception:
        return None


def _extract_table(shape) -> Optional[ExtractedTable]:
    try:
        table = shape.table
        rows: list[list[str]] = []
        for row in table.rows:
            row_cells = []
            for cell in row.cells:
                try:
                    row_cells.append(cell.text or "")
                except Exception:
                    row_cells.append("")
            rows.append(row_cells)
        header_rows = 0
        try:
            header_rows = 1 if table.first_row else 0
        except Exception:
            pass
        col_count = 0
        try:
            col_count = len(table.columns)
        except Exception:
            pass
        return ExtractedTable(rows=rows, header_row_count=header_rows, col_count=col_count)
    except Exception:
        return None


def _collect_slide(slide, geometry: SlideGeometry, index: int, w_emu: int, h_emu: int) -> ExtractedSlide:
    errors: list[str] = []
    shapes: list[ExtractedShape] = []
    charts: list[ExtractedChart] = []
    tables: list[ExtractedTable] = []
    connectors: list[ExtractedConnector] = []

    def walk(shape_iterable) -> None:
        for shape in shape_iterable:
            try:
                shape_type = _shape_type_name(shape)
                if shape_type == "GROUP":
                    walk(shape.shapes)
                    continue
                if shape_type == "LINE":
                    connectors.append(_extract_connector(shape))
                    continue
                if getattr(shape, "has_chart", False):
                    chart = _extract_chart(shape)
                    if chart is not None:
                        charts.append(chart)
                if getattr(shape, "has_table", False):
                    table = _extract_table(shape)
                    if table is not None:
                        tables.append(table)
                extracted = _extract_shape(shape, geometry)
                if extracted is not None:
                    shapes.append(extracted)
            except Exception as exc:  # per-shape resilience
                errors.append(
                    f"shape {getattr(shape, 'shape_id', '?')} "
                    f"({getattr(shape, 'name', '?')}): {exc}"
                )

    walk(slide.shapes)

    notes: Optional[str] = None
    try:
        if slide.has_notes_slide:
            notes_text = slide.notes_slide.notes_text_frame.text
            notes = notes_text if notes_text and notes_text.strip() else None
    except Exception as exc:
        errors.append(f"notes: {exc}")

    layout_name = ""
    try:
        layout_name = slide.slide_layout.name or ""
    except Exception:
        pass

    has_bleed = any(
        s.shape_type == "PICTURE" and s.w >= 0.94 and s.h >= 0.94 for s in shapes
    )

    return ExtractedSlide(
        index=index,
        slide_size_emu=(int(w_emu), int(h_emu)),
        aspect_ratio=aspect_ratio(w_emu, h_emu),
        shapes=shapes,
        charts=charts,
        tables=tables,
        connectors=connectors,
        notes_text=notes,
        layout_name=layout_name,
        has_image_slides_whole_thing=has_bleed,
        extraction_errors=errors,
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def extract_deck(path: Path) -> ExtractedDeck:
    """Open ``path`` and normalise the whole .pptx into an :class:`ExtractedDeck`.

    Raises :class:`InvalidDeckError` for anything that cannot be opened/parsed
    (password-protected files, junk bytes, truncated files, ...).
    """
    path = Path(path)
    try:
        prs = Presentation(str(path))
    except Exception as exc:
        raise InvalidDeckError(f"cannot open {path.name!r}: {exc}") from exc
    try:
        w_emu = int(prs.slide_width) or 0
        h_emu = int(prs.slide_height) or 0
        if not w_emu or not h_emu:
            raise InvalidDeckError(f"{path.name!r} has no slide size")
        geometry = SlideGeometry(w_emu, h_emu)
        slides = [
            _collect_slide(slide, geometry, i, w_emu, h_emu)
            for i, slide in enumerate(prs.slides, start=1)
        ]
        return ExtractedDeck(
            path=str(path),
            slide_count=len(slides),
            size_emu=(w_emu, h_emu),
            slides=slides,
        )
    except InvalidDeckError:
        raise
    except Exception as exc:
        raise InvalidDeckError(f"failed to parse {path.name!r}: {exc}") from exc


def extract_directory(
    folder: Path,
    *,
    use_cache: bool = True,
    on_progress: Optional[Callable[[Path], None]] = None,
    db_path: Optional[Path] = None,
) -> IngestResult:
    """Walk ``folder`` for ``*.pptx`` (recursively) and extract every deck.

    Files are processed in sorted order for deterministic output. ``db_path``
    opts into a specific SQLite cache database (used by tests).
    """
    folder = Path(folder)
    files = sorted(
        {p for p in folder.glob("*.pptx")} | {p for p in folder.glob("**/*.pptx")}
    )
    result = IngestResult()
    cache = IngestCache(db_path) if use_cache else None
    try:
        for path in files:
            if on_progress is not None:
                on_progress(path)
            try:
                file_hash = deck_hash(path)
            except OSError as exc:
                result.errors.append(IngestError(path, f"unreadable file: {exc}"))
                continue
            if cache is not None:
                cached = cache.get(file_hash)
                if cached is not None:
                    result.cached_hits += 1
                    result.decks.append(cached)
                    continue
            try:
                deck = extract_deck(path)
            except InvalidDeckError as exc:
                result.errors.append(IngestError(path, str(exc)))
                if cache is not None:
                    cache.record_error(str(path), str(exc))
                continue
            result.new_parses += 1
            result.decks.append(deck)
            if cache is not None:
                cache.put(file_hash, deck)
    finally:
        if cache is not None:
            cache.close()
    return result

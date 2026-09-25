"""Deterministic synthetic corpus generator (DeckForge Workstream A).

Builds ``*.pptx`` decks into ``{out}/deck_{index:02d}.pptx`` and a per-deck
``*.slides.json`` sidecar recording exactly what the generator wrote, per
slide: every text string in document (insertion) order — the exact order the
read-side parser walks the shapes — the notes text, plus archetype, theme,
aspect-ratio and chart/table/connector payloads.

Every non-title slide expresses a real structural signature so the analysis
side (Workstream B) detects a *variety* of archetypes: charts, tables, image
placements, cards, columns, timelines, process flows, portraits, quotes and
statements are all produced with coordinates that match the heuristic rules.

Determinism
-----------
* Every random draw flows through ``random.Random(f"{seed}:{deck__index}")``.
  CPython seeds strings deterministically (SHA-512 over the UTF-8 bytes), so the
  same ``(seed, deck_index)`` always yields the same byte sequence on any
  machine and any run.
* ``core_properties.created`` / ``modified`` are pinned to fixed values; no
  wall-clock, ``datetime.now()`` or other entropy source is used.
* Each ``.pptx`` is a zip archive; python-pptx stamps per-entry local
  timestamps into it, so we re-zip every archive with fixed per-entry dates
  (see :func:`_deterministic_zip`) to keep the *bytes* byte-identical across
  machines, runs and seeds. Generated images are PIL PNGs with no metadata.
* Chart slides embed an xlsx workbook python-pptx writes with the wall-clock
  time; the creation timestamp is pinned the same way the renderer pins it
  (see the ``xlsxwriter`` monkeypatch), so even that embedded blob is stable.
"""

from __future__ import annotations

import argparse
import io
import json
import random
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipInfo

import xlsxwriter.workbook as _xlsxworkbook
from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.util import Inches, Pt

from deckforge_core.schemas.archetypes import ARCHETYPE_ORDER

PINNED_CREATED = datetime(2024, 3, 16, 9, 30, 0)
PINNED_MODIFIED = datetime(2024, 3, 16, 9, 30, 0)
PINNED_ZIP_DT = (2024, 3, 16, 9, 30, 0)
PINNED_WORKBOOK_TS = datetime(2024, 3, 16, 9, 30, 0, tzinfo=timezone.utc)

THEMES = {
    "work-sans-corporate": (
        "Work Sans", "Arial", "1F2937", "2563EB", "6B7280", "F3F4F6",
    ),
    "calibri-slate": (
        "Calibri", "Arial", "0B2545", "0B6E99", "5B7A9D", "EEF4FA",
    ),
    "georgia-editorial": (
        "Georgia", "Arial", "1A1A1A", "A93226", "6E6E6E", "F7F5F0",
    ),
    "poppins-playful": (
        "Poppins", "Arial", "21223E", "FF4785", "8A8FA3", "F7F7FF",
    ),
}
KICKERS = ["STRATEGY", "GROWTH", "OPERATIONS", "PRODUCT", "Q3 2026",
           "EXECUTIVE BRIEF", "BOARD SUMMARY", "FIELD REPORT"]
TITLES = [
    "Scaling the engine without scaling the cost",
    "The roadmap behind the revenue curve",
    "Operating cadence for the next four quarters",
    "Building the category, not just the company",
    "Where the plan bends and where it holds",
    "A deliberate year of compounding",
    "The operating model, refreshed",
    "Ship the platform; keep the calendar thin",
]
SUBJECTS = [
    "What changed, what we decided, and what is next.",
    "Prepared for the executive team and the board.",
    "A working document; decisions are bolded and owned.",
    "From the strategy studio ahead of the quarterly review.",
]
BODY_BANK = [
    "We moved the bottleneck out of the critical path last quarter.",
    "Every team now owns a number, and every number has an owner.",
    "The plan is a contract we renew each quarter with an explicit ask.",
    "Speed is the report card of a healthy operating model.",
    "We earn the right to grow fast by growing deliberately.",
    "Momentum is compounded focus, reviewed on a fixed cadence.",
]
QUOTES = [
    "A plan without an owner is a wish list.",
    "We do not get faster by sprinting; we get faster by shipping.",
    "The bottleneck is always the decision, not the tooling.",
    "Strong teams design their own substrate.",
]
QUOTE_AUTHORS = [
    "— the operating committee", "— product leadership", "— field ops",
    "— the strategy studio",
]
SPEAKERS = ["CEO", "COO", "VP Product", "Head of Growth", "CTO"]
AGENDA = ["Where we are", "The gap", "What unlocks", "Risk register", "The ask"]
STAT_LABELS = ["Revenue", "Bookings", "NPS", "Churn", "Margins", "Users"]
STAT_VALUES = ["38%", "2.4x", "91", "4.8", "$4.2", "12", "3.5x", "66"]
TEAM = ["Amara Okafor", "Jonas Berg", "Priya Rao", "Marcus Chen",
        "Ines Vera", "Tariq Haddad", "Nozomi Tanaka", "Elena Silva"]
ROLES = ["Product Lead", "Data Science", "Design Ops", "Platform",
         "Growth", "Analytics"]
CARD_HEADS = ["Bookings", "NPS", "Users", "Margins"]
CARD_BODIES = [
    "Bookings grew 2.4x against a deliberate plan.",
    "Ninety-one — a new high-water mark this quarter.",
    "Margins up 4.8 points with headcount flat.",
    "Users up 38% year over year with the same cadence.",
]
QUOTE_BANK = QUOTES
CHART_CATEGORIES = ["Q1", "Q2", "Q3", "Q4"]
TABLE_DATA = [
    ["Metric", "Actual", "Plan", "Delta"],
    ["Revenue", "$4.2M", "$3.9M", "+7.7%"],
    ["Bookings", "$12M", "$10M", "+20%"],
    ["NPS", "91", "85", "+6"],
    ["Churn", "4.2%", "5.0%", "−0.8"],
]
COMPARISON_HEADINGS = ["Keep", "Cut"]
COMPARISON_ROWS = [
    "The cadence that made last quarter work",
    "A second review cycle every two weeks",
    "The single number every team owns",
    "Reports that arrive after the decision",
]
STATEMENTS = [
    "The gap is an operating gap, not a talent gap.",
    "We outgrew our own scoring system last quarter.",
    "Two decisions drive ninety percent of the upside.",
    "Ownership is the scarcest resource we have.",
]
SOURCES = ["Source: internal analytics", "Source: board pack", "Source: field notes"]
TIMELINE_EVENTS = [
    ("2024", "Pilot runs, two teams"),
    ("2025", "Platform extraction begins"),
    ("2026", "Self-serve for most teams"),
    ("2027", "Async cadence everywhere"),
]
FLOW_STEPS = [
    ("Decide", "One owner, one date"),
    ("Ship", "Small batches only"),
    ("Measure", "Same metric every time"),
    ("Adjust", "Feed results back in"),
]
CARD_FILL_LIGHT = "EEF4FA"

_CONNECTOR_LINE = ("2563EB", "6B7280", "B03A2E", "FF4785")
_STAT_ROWS = list(zip(STAT_LABELS, STAT_VALUES))


def _rgb(hexstr: str) -> RGBColor:
    return RGBColor.from_string(hexstr)


def _install_workbook_timestamp_pin() -> None:
    """Pin the embedded chart workbook's creation time (deterministic builds)."""
    original = _xlsxworkbook.Workbook.__init__

    def _pinned(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.createtime = PINNED_WORKBOOK_TS
        self.set_properties({"created": PINNED_WORKBOOK_TS})

    if original is not _pinned:
        _xlsxworkbook.Workbook.__init__ = _pinned


_install_workbook_timestamp_pin()


def _add_textbox(slide, x, y, w, h, paras, *, name="body", wrap=True):
    """Add a text box; append each paragraph text in order. Returns the strings
    in exactly the document order the parser will read from this box."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tb.name = name
    tf = tb.text_frame
    tf.word_wrap = wrap
    out = []
    for i, (text, size, bold, color, font) in enumerate(paras):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        run = para.add_run()
        run.text = text
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.name = font
        run.font.color.rgb = _rgb(color)
        out.append(text)
    return out


def _add_column(slide, x, y, w, h, fill_hex, line_hex, paras, *, name="column", wrap=True):
    """Rounded-rectangle shape with a text frame (cards, boxes, ...)."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h)
    )
    shape.name = name
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(fill_hex)
    shape.line.color.rgb = _rgb(line_hex)
    shape.line.width = Pt(1.0)
    tf = shape.text_frame
    tf.word_wrap = wrap
    tf.margin_left = Inches(0.15)
    tf.margin_right = Inches(0.15)
    tf.margin_top = Inches(0.12)
    tf.margin_bottom = Inches(0.12)
    out = []
    for i, (text, size, bold, color, font) in enumerate(paras):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        run = para.add_run()
        run.text = text
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.name = font
        run.font.color.rgb = _rgb(color)
        out.append(text)
    return out


def _add_picture(slide, x, y, w, h, color_hex, *, name="image"):
    rgb = _rgb(color_hex)
    im = Image.new("RGB", (96, 96), (rgb[0], rgb[1], rgb[2]))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    slide.shapes.add_picture(buf, Inches(x), Inches(y), Inches(w), Inches(h)).name = name


def _add_connector(slide, x1, y1, x2, y2, *, color_hex, name="connector"):
    conn = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1),
        Inches(x2), Inches(y2))
    conn.line.color.rgb = _rgb(color_hex)
    conn.name = name


def _add_chart(slide, x, y, w, h):
    chart_data = CategoryChartData()
    chart_data.categories = list(CHART_CATEGORIES)
    chart_data.add_series("Planned", (1.0, 1.2, 1.4, 1.6))
    chart_data.add_series("Actual", (1.1, 1.3, 1.5, 1.8))
    slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h),
        chart_data,
    )


def _add_table(slide, x, y, w, h):
    rows = len(TABLE_DATA)
    cols = len(TABLE_DATA[0])
    table = slide.shapes.add_table(rows, cols, Inches(0), Inches(0), Inches(0), Inches(0))
    table.left = Inches(x)
    table.top = Inches(y)
    table.width = Inches(w)
    table.height = Inches(h)
    for r, row in enumerate(TABLE_DATA):
        for c, value in enumerate(row):
            cell = table.table.cell(r, c)
            cell.text = value
    return table


def _add_notes(slide, text: str) -> None:
    slide.notes_slide.notes_text_frame.text = text


def _deterministic_zip(path: Path) -> None:
    """Re-zip a .pptx with fixed per-entry date_time so bytes are reproducible
    regardless of build-machine wall-clock."""
    tmp = path.with_suffix(".det.pptx")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w",
                                                        ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            zi = ZipInfo(info.filename, PINNED_ZIP_DT)
            zi.compress_type = ZIP_DEFLATED
            zout.writestr(zi, zin.read(info.filename))
    tmp.replace(path)


# --------------------------------------------------------------------------- #
# Per-archetype structure builders
# --------------------------------------------------------------------------- #
# Each builder appends real shapes (text boxes, pictures, charts, tables,
# connectors) so the read-side archetype heuristics classify the slide as its
# archetype. Builders return only the document-order text strings for the
# sidecar (table cell text and chart data are not shapes and are omitted).


def _base_content(slide, rng, texts, head_font, body_font, accent_hex,
                  head_hex):
    kicker = rng.choice(KICKERS)
    texts += _add_textbox(
        slide, 0.55, 0.45, 12.0, 0.5,
        [(kicker, 13, True, accent_hex, body_font)], name="kicker")
    title = rng.choice(TITLES)
    texts += _add_textbox(
        slide, 0.55, 0.85, 12.0, 0.7,
        [(title, 26, True, head_hex, head_font)], name="title")


def _builder_big_number(slide, meta, rng, head_font, body_font, accent_hex,
                        head_hex, muted_hex):
    texts = meta["texts"]
    label, value = rng.choice(_STAT_ROWS)
    texts += _add_textbox(
        slide, 0.55, 0.45, 12.0, 0.5,
        [(label.upper(), 13, True, accent_hex, body_font)], name="kicker")
    texts += _add_textbox(
        slide, 0.55, 1.6, 12.2, 2.2,
        [(value, 66, True, accent_hex, head_font)], name="number")
    texts += _add_textbox(
        slide, 0.55, 3.9, 9.5, 0.8,
        [("Monthly " + label.lower() + " after this quarter's rework.",
          14, False, muted_hex, body_font)], name="caption")
    return "big-number"


def _builder_quote(slide, meta, rng, head_font, body_font, accent_hex, head_hex,
                   muted_hex):
    texts = meta["texts"]
    texts += _add_textbox(
        slide, 0.55, 1.8, 12.2, 2.2,
        [(f"“{rng.choice(QUOTES)}”", 28, False, head_hex, head_font)],
        name="quote")
    texts += _add_textbox(
        slide, 0.55, 4.2, 9.5, 0.6,
        [(rng.choice(QUOTE_AUTHORS), 16, False, muted_hex, body_font)],
        name="author")
    return "quote"


def _builder_chart(slide, meta, rng, head_font, body_font, accent_hex, head_hex,
                   muted_hex):
    _base_content(slide, rng, meta["texts"], head_font, body_font,
                  accent_hex, head_hex)
    _add_chart(slide, 0.55, 1.7, 12.2, 5.2)
    meta["chart"] = {"categories": CHART_CATEGORIES}
    return "chart"


def _builder_table(slide, meta, rng, head_font, body_font, accent_hex, head_hex,
                   muted_hex):
    _base_content(slide, rng, meta["texts"], head_font, body_font,
                  accent_hex, head_hex)
    _add_table(slide, 0.55, 1.7, 12.2, 5.0)
    meta["table"] = {"rows": len(TABLE_DATA), "cols": len(TABLE_DATA[0])}
    return "table"


def _builder_statement(slide, meta, rng, head_font, body_font, accent_hex,
                       head_hex, muted_hex):
    texts = meta["texts"]
    texts += _add_textbox(
        slide, 0.55, 1.9, 12.2, 2.0,
        [(rng.choice(STATEMENTS), 34, True, head_hex, head_font)], name="statement")
    texts += _add_textbox(
        slide, 0.55, 4.0, 9.5, 0.6,
        [(rng.choice(SOURCES), 20, False, muted_hex, body_font)], name="source")
    return "statement"


def _builder_closing(slide, meta, rng, head_font, body_font, accent_hex,
                     head_hex, muted_hex):
    texts = meta["texts"]
    texts += _add_textbox(
        slide, 0.55, 2.3, 12.2, 1.0,
        [("Thank you.", 18, True, head_hex, head_font)], name="closing")
    texts += _add_textbox(
        slide, 0.55, 3.3, 12.2, 0.8,
        [("Questions welcome — reach the team anytime.", 18, False, muted_hex,
          body_font)], name="contact")
    return "closing"


def _builder_image_left(slide, meta, rng, head_font, body_font, accent_hex,
                        head_hex, muted_hex):
    _base_content(slide, rng, meta["texts"], head_font, body_font,
                  accent_hex, head_hex)
    _add_picture(slide, 0.55, 1.4, 4.6, 3.4, accent_hex, name="portrait")
    return "image-left"


def _builder_image_right(slide, meta, rng, head_font, body_font, accent_hex,
                         head_hex, muted_hex):
    _base_content(slide, rng, meta["texts"], head_font, body_font,
                  accent_hex, head_hex)
    _add_picture(slide, 8.1, 1.4, 4.6, 3.4, accent_hex, name="portrait")
    return "image-right"


def _builder_full_bleed(slide, meta, rng, head_font, body_font, accent_hex,
                        head_hex, muted_hex):
    _add_picture(slide, 0.05, 0.05, 13.23, 7.4, accent_hex, name="cover")
    meta["texts"] += _add_textbox(
        slide, 1.0, 0.6, 11.3, 0.5,
        [(rng.choice(KICKERS), 13, True, "FFFFFF", body_font)], name="kicker")
    meta["texts"] += _add_textbox(
        slide, 1.0, 1.1, 11.3, 1.0,
        [(rng.choice(TITLES), 30, True, "FFFFFF", head_font)], name="title")
    return "full-bleed-image"


def _builder_three_cards(slide, meta, rng, head_font, body_font, accent_hex,
                         head_hex, muted_hex):
    _base_content(slide, rng, meta["texts"], head_font, body_font,
                  accent_hex, head_hex)
    chosen = rng.sample(list(zip(CARD_HEADS, CARD_BODIES)), 3)
    for i, (head, body) in enumerate(chosen):
        x = 0.8 + i * (3.9 + 0.3)
        meta["texts"] += _add_column(
            slide, x, 1.5, 3.9, 4.5, CARD_FILL_LIGHT, accent_hex,
            [(head, 20, True, head_hex, head_font),
             (body, 13, False, muted_hex, body_font)],
            name=f"card_{i + 1}")
    return "three-cards"


def _builder_comparison(slide, meta, rng, head_font, body_font, accent_hex,
                        head_hex, muted_hex):
    _base_content(slide, rng, meta["texts"], head_font, body_font,
                  accent_hex, head_hex)
    left_words, right_words = COMPARISON_HEADINGS
    left_body = " ".join(COMPARISON_ROWS[:2])
    right_body = " ".join(COMPARISON_ROWS[2:])
    for col, (heading, body) in enumerate(
            ((left_words, left_body), (right_words, right_body))):
        x = 0.8 + col * 6.6
        meta["texts"] += _add_textbox(slide, x, 1.6, 5.4, 0.5,
                     [(heading, 19, True, accent_hex, head_font)],
                     name=f"heading_{col + 1}")
        meta["texts"] += _add_textbox(slide, x, 2.2, 5.4, 3.6,
                     [(body, 14, False, muted_hex, body_font)],
                     name=f"body_{col + 1}")
    return "comparison"


def _builder_two_column(slide, meta, rng, head_font, body_font, accent_hex,
                        head_hex, muted_hex):
    _base_content(slide, rng, meta["texts"], head_font,
                  body_font, accent_hex, head_hex)
    for col in (1, 2):
        body = " ".join([rng.choice(BODY_BANK), rng.choice(BODY_BANK)])
        meta["texts"] += _add_textbox(slide, 0.8 + (col - 1) * 6.6, 1.7, 5.4, 4.2,
                     [(body, 14, False, muted_hex, body_font)],
                     name=f"body_{col}")
    return "two-column-text"


def _builder_agenda(slide, meta, rng, head_font, body_font, accent_hex,
                    head_hex, muted_hex):
    texts = meta["texts"]
    texts += _add_textbox(
        slide, 0.55, 0.8, 12.0, 0.7,
        [(rng.choice(TITLES), 24, True, head_hex, head_font)], name="title")
    items = [(rng.choice(AGENDA), 14, False, muted_hex, body_font) for _ in range(5)]
    texts += _add_textbox(slide, 1.0, 1.7, 8.5, 4.6, items, name="agenda")
    return "agenda"


def _builder_timeline(slide, meta, rng, head_font, body_font, accent_hex,
                      head_hex, muted_hex):
    _base_content(slide, rng, meta["texts"], head_font, body_font,
                  accent_hex, head_hex)
    events = TIMELINE_EVENTS
    for i, (year, event) in enumerate(events):
        x = 0.6 + i * 3.2
        meta["texts"] += _add_column(
            slide, x, 1.7, 2.85, 1.7, CARD_FILL_LIGHT, accent_hex,
            [(year, 18, True, accent_hex, head_font),
             (event, 13, False, muted_hex, body_font)],
            name=f"timeline_{i + 1}")
    _add_connector(slide, 0.6, 2.5, 12.5, 2.5, color_hex=accent_hex,
                   name="timeline_line")
    return "timeline"


def _builder_process_flow(slide, meta, rng, head_font, body_font, accent_hex,
                          head_hex, muted_hex):
    _base_content(slide, rng, meta["texts"], head_font, body_font,
                  accent_hex, head_hex)
    steps = FLOW_STEPS
    for i, (step, detail) in enumerate(steps):
        y = 1.3 + i * 1.45
        meta["texts"] += _add_column(
            slide, 4.7, y, 4.0, 1.05, CARD_FILL_LIGHT, accent_hex,
            [(step, 15, True, head_hex, head_font),
             (detail, 12, False, muted_hex, body_font)],
            name=f"step_{i + 1}")
        if i < len(steps) - 1:
            _add_connector(slide, 6.7, y + 1.05, 6.7, y + 1.45,
                           color_hex=accent_hex, name=f"connector_{i + 1}")
    return "process-flow"


def _builder_team(slide, meta, rng, head_font, body_font, accent_hex,
                  head_hex, muted_hex):
    _base_content(slide, rng, meta["texts"], head_font, body_font,
                  accent_hex, head_hex)
    names = rng.sample(TEAM, 3)
    roles = [rng.choice(ROLES) for _ in names]
    for i, (person, role) in enumerate(zip(names, roles)):
        x = 0.9 + i * 4.8
        _add_picture(slide, x, 1.4, 2.0, 2.2, accent_hex, name=f"portrait_{i + 1}")
        meta["texts"] += _add_textbox(slide, x, 3.75, 2.0, 1.6,
                     [(person, 16, True, head_hex, head_font),
                      (role, 13, False, muted_hex, body_font)],
                     name=f"name_{i + 1}")
    return "team"


_BUILDERS: dict[str, Any] = {
    "big-number": _builder_big_number,
    "quote": _builder_quote,
    "chart": _builder_chart,
    "table": _builder_table,
    "statement": _builder_statement,
    "closing": _builder_closing,
    "image-left": _builder_image_left,
    "image-right": _builder_image_right,
    "full-bleed-image": _builder_full_bleed,
    "three-cards": _builder_three_cards,
    "comparison": _builder_comparison,
    "two-column-text": _builder_two_column,
    "agenda": _builder_agenda,
    "timeline": _builder_timeline,
    "process-flow": _builder_process_flow,
    "team": _builder_team,
}

assert set(ARCHETYPE_ORDER) == set(_BUILDERS) | {"title", "section-divider"}, (
    "corpus builders must cover every canonical archetype"
)


def build_deck(out_dir: Path, deck_index: int, seed: int,
               slide_w: float = 13.333, slide_h: float = 7.5) -> tuple[Path, dict[str, Any]]:
    """Build one deterministic deck. Returns (pptx_path, sidecar_dict)."""
    rng = random.Random(f"{seed}:{deck_index}")
    theme_names = list(THEMES)
    theme_slug = rng.choice(theme_names)
    kicker = rng.choice(KICKERS)
    title = rng.choice(TITLES)
    subject = rng.choice(SUBJECTS)
    head_font, body_font, head_hex, accent_hex, muted_hex, _ = THEMES[theme_slug]

    prs = Presentation()
    prs.slide_width = Inches(slide_w)
    prs.slide_height = Inches(slide_h)
    cp = prs.core_properties
    cp.created = PINNED_CREATED
    cp.modified = PINNED_MODIFIED
    cp.last_modified_by = "deckforge-corpus"
    cp.author = "DeckForge Synthetic Corpus"
    cp.title = f"Deck {deck_index}"

    def add_slide(archetype: str):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        meta = {"index": len(slides_meta), "archetype": archetype,
                "texts": [], "notes": ""}
        slides_meta.append(meta)
        return slide, meta

    slides_meta: list[dict[str, Any]] = []

    # Slide 0: title
    slide, meta = add_slide("title")
    meta["texts"] += _add_textbox(slide, 0.55, 2.3, 12.0, 0.64,
                                  [(kicker, 13, True, accent_hex, body_font)],
                                  name="kicker")
    meta["texts"] += _add_textbox(slide, 0.55, 2.85, 12.0, 1.2,
                                  [(title, 40, True, head_hex, head_font)],
                                  name="title")
    meta["texts"] += _add_textbox(slide, 0.55, 4.05, 8.6, 0.72,
                                  [(subject, 16, False, muted_hex, body_font)],
                                  name="subtitle")
    meta["notes"] = "Ask: sign off the sequencing for Q3."
    _add_notes(slide, meta["notes"])

    # Slide 1: section divider (28pt heading, so title/subtitle rules don't fire)
    slide, meta = add_slide("section-divider")
    meta["texts"] += _add_textbox(slide, 0.55, 2.3, 12.0, 0.64,
                                  [(kicker, 13, True, accent_hex, body_font)],
                                  name="kicker")
    meta["texts"] += _add_textbox(slide, 0.55, 2.9, 12.0, 1.0,
                                  [(rng.choice(TITLES), 28, True, head_hex, head_font)],
                                  name="title")
    meta["notes"] = "Section divider."
    _add_notes(slide, meta["notes"])

    # Slides 2..12: eleven real structures sampled per deck (deterministic via
    # rng). Every deck carries the same number so round-trip slide counts hold.
    order = rng.sample(sorted(_BUILDERS), 11)
    for i, archetype in enumerate(order, start=2):
        slide, meta = add_slide(archetype)
        builder = _BUILDERS[archetype]
        builder(slide, meta, rng, head_font, body_font, accent_hex, head_hex,
                muted_hex)
        meta["notes"] = f"Notes for slide {i} ({archetype})."
        _add_notes(slide, meta["notes"])

    pptx_path = out_dir
    prs.save(pptx_path)
    _deterministic_zip(pptx_path)

    sidecar = {
        "path": pptx_path.name, "seed": seed, "deck_index": deck_index,
        "theme": theme_slug, "aspect": "16:9", "slides": slides_meta,
    }
    return pptx_path, sidecar


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate the synthetic corpus.")
    ap.add_argument("--out", type=Path, default=Path("corpus/raw"))
    ap.add_argument("--decks", type=int, default=32)
    ap.add_argument("--seed", type=int, default=20240316)
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    summary = {"seed": args.seed, "decks": []}
    for deck_index in range(args.decks):
        pptx_path, sidecar = build_deck(args.out / f"deck_{deck_index:02d}.pptx",
                                        deck_index, args.seed)
        sidecar_path = args.out / f"deck_{deck_index:02d}.slides.json"
        sidecar_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
        summary["decks"].append(sidecar_path.as_posix())
    (args.out / "_corpus_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {args.decks} decks to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

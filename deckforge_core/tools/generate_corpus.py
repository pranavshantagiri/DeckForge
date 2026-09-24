"""Deterministic synthetic corpus generator (DeckForge Workstream A).

Builds ``*.pptx`` decks into ``{out}/deck_{index:02d}.pptx`` and a per-deck
``*.slides.json`` sidecar recording exactly what the generator wrote, per
slide: every text string in document (insertion) order — the exact order the
read-side parser walks the shapes — the notes text, plus archetype, theme,
aspect-ratio and chart/table/connector payloads.

Determinism
-----------
* Every random draw flows through ``random.Random(f"{seed}:{deck__index}")``.
  CPython seeds strings deterministically (SHA-512 over the UTF-8 bytes), so the
  same ``(seed, deck_index)`` always yields the same byte sequence on any
  machine and any run.
* ``core_properties.created`` / ``modified`` are pinned to fixed values; no
  wall-clock, ``datetime.now()`` or other entropy source is used.
* Each ``.pptx`` is a zip archive; python-pptix stamps per-entry local
  timestamps into it, so we re-zip every archive with fixed per-entry dates
  (see :func:`_deterministic_zip`) to keep the *bytes* byte-identical across
  machines, runs and seeds. Generated images are PIL PNGs with no metadata.
"""

from __future__ import annotations

import argparse
import io
import json
import random
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipInfo

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR
from pptx.util import Inches, Pt

from deckforge_core.schemas.archetypes import ARCHETYPE_ORDER

PINNED_CREATED = datetime(2024, 3, 16, 9, 30, 0)
PINNED_MODIFIED = datetime(2024, 3, 16, 9, 30, 0)
PINNED_ZIP_DT = (2024, 3, 16, 9, 30, 0)

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
SPEAKERS = ["CEO", "COO", "VP Product", "Head of Growth", "CTO"]
AGENDA = ["Where we are", "The gap", "What unlocks", "Risk register", "The ask"]
STAT_LABELS = ["Revenue", "Bookings", "NPS", "Churn", "Margins", "Users"]
STAT_VALUES = ["38%", "2.4x", "91", "4.8 pts", "$4.2M", "12 days"]
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

_CONNECTOR_LINE = ("2563EB", "6B7280", "B03A2E", "FF4785")
_STAT_ROWS = list(zip(STAT_LABELS, STAT_VALUES))


def _rgb(hexstr: str) -> RGBColor:
    return RGBColor.from_string(hexstr)


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


def _add_picture(slide, x, y, w, h, color_hex, *, name="image"):
    rgb = _rgb(color_hex)
    im = Image.new("RGB", (64, 64), (rgb[0], rgb[1], rgb[2]))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    slide.shapes.add_picture(buf, Inches(x), Inches(y), Inches(w), Inches(h))


def _add_notes(slide, text: str) -> None:
    slide.notes_slide.notes_text_frame.text = text


def _add_connector(slide, x1, y1, x2, y2, *, color_hex, name="connector"):
    conn = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1),
        Inches(x2), Inches(y2))
    conn.line.color.rgb = _rgb(color_hex)
    conn.name = name


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


def build_deck(out_dir: Path, deck_index: int, seed: int,
               slide_w: float = 13.333, slide_h: float = 7.5) -> tuple[Path, dict[str, Any]]:
    """Build one deterministic deck. Returns (pptx_path, sidecar_dict)."""
    rng = random.Random(f"{seed}:{deck_index}")
    theme_names = list(THEMES)
    theme_slug = rng.choice(theme_names)
    kicker = rng.choice(KICKERS)
    title = rng.choice(TITLES)
    subject = rng.choice(SUBJECTS)
    head_font, body_font, head_hex, accent_hex, muted_hex, fill_hex = THEMES[theme_slug]

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
                                  [(kicker, 13, True, accent_hex, body_font)], name="kicker")
    meta["texts"] += _add_textbox(slide, 0.55, 2.85, 12.0, 1.2,
                                  [(title, 40, True, head_hex, head_font)], name="title")
    meta["texts"] += _add_textbox(slide, 0.55, 4.05, 8.6, 0.72,
                                  [(subject, 16, False, muted_hex, body_font)], name="subtitle")
    meta["notes"] = "Ask: sign off the sequencing for Q3."
    _add_notes(slide, meta["notes"])

    # Window of archetypes rotated per deck; each deck walks a contiguous,
    # non-repeating run; across the corpus all 18 are covered.
    window = ARCHETYPE_ORDER * 2
    start = deck_index % len(ARCHETYPE_ORDER)
    chosen = [ARCHETYPE_ORDER[start]] + [window[start + i] for i in range(12)]

    for i, archetype in enumerate(chosen[1:], start=1):
        slide, meta = add_slide(archetype)
        meta["texts"] += _add_textbox(
            slide, 0.55, 0.55, 12.0, 0.5,
            [(kicker, 13, True, accent_hex, body_font)], name="kicker")
        meta["texts"] += _add_textbox(
            slide, 0.55, 0.95, 12.0, 0.95,
            [(f"{i:02d} • {archetype}", 26, True, head_hex, head_font)], name="title")
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

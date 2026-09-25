"""Slide feature vectors for clustering (Workstream B).

A fixed-length, mostly-normalised numeric vector per slide so that structurally
similar slides land near each other regardless of deck size or aspect ratio.
Features are cheap and deterministic; the vision pass is deferred (optional per
spec), so nothing here inspects pixels.

Geometry is read in RELATIVE units (0..1 fractions) straight from the ingest
contract.
"""

from __future__ import annotations

import numpy as np

from deckforge_core.schemas.extracted import (
    ExtractedSlide,
    image_area_fraction,
    text_area_fraction,
    text_density,
    total_words,
)

#: Width of the fixed feature vector returned by :func:`slide_features`.
FEATURE_DIM = 13

#: Human labels aligned with the vector layout (same index order).
FEATURE_NAMES = [
    "word_count",
    "image_area_fraction",
    "text_area_fraction",
    "shape_count",
    "has_chart",
    "has_table",
    "big_number",
    "bullet_count",
    "title_word_count",
    "has_connectors",
    "has_notes",
    "text_density",
    "is_full_bleed",
]

_WORD_DIVISOR = 100.0
_SHAPE_DIVISOR = 20.0
_BULLET_DIVISOR = 10.0
_TITLE_WORD_DIVISOR = 25.0
_DENSITY_DIVISOR = 300.0
_BIG_NUMBER_PT = 32.0
_FULL_BLEED_AREA = 0.8


def bullet_paragraphs(slide: ExtractedSlide) -> int:
    """Count list-like paragraphs: non-first paragraphs in a text frame plus
    paragraphs whose text begins with a bullet or dash glyph."""
    count = 0
    for shape in slide.shapes:
        paras = [p for p in shape.text if p.text().strip()]
        for idx, para in enumerate(paras):
            text = para.text().strip()
            if idx > 0 or text[:1] in ("\u2022", "\uf0b7", "-", "\u2013", "*", "\u203a"):
                count += 1
    return count


def largest_run_pt(slide: ExtractedSlide) -> float:
    """Largest font size (pt) across every run on the slide; 0 when no text."""
    best = 0.0
    for shape in slide.shapes:
        for para in shape.text:
            for run in para.runs:
                if run.size_pt and run.size_pt > best:
                    best = float(run.size_pt)
    return best


def title_shape(slide: ExtractedSlide):
    """The shape carrying the slide's largest run; ``None`` when no text."""
    return max(
        (s for s in slide.shapes if any(p.text().strip() for p in s.text)),
        key=lambda s: _shape_max_pt(s),
        default=None,
    )


def _shape_max_pt(shape) -> float:
    best = 0.0
    for para in shape.text:
        for run in para.runs:
            if run.size_pt and run.size_pt > best:
                best = float(run.size_pt)
    return best


def slide_features(slide: ExtractedSlide) -> np.ndarray:
    """Return the fixed-length feature vector (see ``FEATURE_NAMES``).

    ``big_number`` is a boolean (any run >= 32pt); ``is_full_bleed`` flags an
    image covering more than 80% of the slide. Degenerate values are clamped to
    [0, 1].
    """
    words = total_words(slide)
    im_area = image_area_fraction(slide)
    tx_area = text_area_fraction(slide)
    max_pt = largest_run_pt(slide)
    title = title_shape(slide)

    features = np.array(
        [
            min(words / _WORD_DIVISOR, 1.0),
            min(im_area, 1.0),
            min(tx_area, 1.0),
            min(len(slide.shapes) / _SHAPE_DIVISOR, 1.0),
            1.0 if slide.charts else 0.0,
            1.0 if slide.tables else 0.0,
            1.0 if max_pt >= _BIG_NUMBER_PT else 0.0,
            min(bullet_paragraphs(slide) / _BULLET_DIVISOR, 1.0),
            min((title.word_count() if title is not None else 0) / _TITLE_WORD_DIVISOR, 1.0),
            1.0 if slide.connectors else 0.0,
            1.0 if slide.notes_text else 0.0,
            min(text_density(slide) / _DENSITY_DIVISOR, 1.0),
            1.0 if im_area > _FULL_BLEED_AREA else 0.0,
        ],
        dtype=float,
    )
    return features

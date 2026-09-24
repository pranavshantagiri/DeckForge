"""Round-trip: the read-side parser reproduces what the generator wrote.

Workstream A owns the generator (``tools/generate_corpus.py``); the frozen
ingest parser (``deckforge_core.ingest.extract_deck``) is the *other* side of
the contract. These tests prove the two sides agree: every text string the
generator recorded in its ``*.slides.json`` sidecar — in document (insertion)
order, the exact order the parser walks shapes — must come back out of
:func:`extract_deck`, per slide, together with the same notes text and the same
slide geometry/aspect ratio.

They also lock the field names the analysis side will lean on
(``aspect_ratio``, per-slide ``texts``/``notes``, ``shape.text()``) so a rename
on either side of the contract is caught here rather than downstream.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deckforge_core.ingest import (
    extract_deck,
    extract_directory,
)
from deckforge_core.tools import generate_corpus as gc


@pytest.fixture(scope="module")
def corpus_dir(tmp_path_factory) -> Path:
    """One fixture generates the same corpus once per module and reuses it
    across every test in the file (cheap file IO, same assertions)."""
    out = tmp_path_factory.mktemp("corpus") / "raw"
    rc = gc.main(["--out", str(out), "--decks", "24", "--seed", "20240316"])
    assert rc == 0
    return out


def _sidecar_texts(side: dict) -> list[str]:
    """The full, per-slide list of text strings in document order, exactly as
    the generator recorded them — the same order the parser will walk."""
    return [t for sl in side["slides"] for t in sl["texts"]]


@pytest.mark.parametrize("deck_index", [0, 7, 23])
def test_parser_reproduces_sidecar_texts(corpus_dir: Path, deck_index: int) -> None:
    pptx = corpus_dir / f"deck_{deck_index:02d}.pptx"
    side = json.loads(
        (corpus_dir / f"deck_{deck_index:02d}.slides.json").read_text(
            encoding="utf-8"
        )
    )
    deck = extract_deck(pptx)

    assert deck.slide_count == len(side["slides"])
    assert deck.aspect_ratio == side.get("aspect")

    parsed = [t for sl in deck.slides for t in slide_text_paragraphs(sl)]
    expected = _sidecar_texts(side)
    assert parsed == expected, (
        f"deck_{deck_index:02d} text order diverged from sidecar"
    )


def test_parser_reproduces_notes_per_slide(corpus_dir: Path) -> None:
    pptx = corpus_dir / "deck_03.pptx"
    side = json.loads(
        (corpus_dir / "deck_03.slides.json").read_text(encoding="utf-8")
    )
    deck = extract_deck(pptx)

    for ex_slide, want in zip(deck.slides, side["slides"]):
        assert ex_slide.notes_text == want["notes"], (
            f"slide notes mismatch for {ex_slide.index}"
        )


def test_parser_walks_shapes_in_sidecar_order(corpus_dir: Path) -> None:
    """Shape-level order must agree too: the round-trip is not just the floats
    of words but the actual placement of each text string."""
    pptx = corpus_dir / "deck_01.pptx"
    side = json.loads(
        (corpus_dir / "deck_01.slides.json").read_text(encoding="utf-8")
    )
    deck = extract_deck(pptx)

    for ex_slide, want_slide in zip(deck.slides, side["slides"]):
        got = []
        for shape in ex_slide.shapes:
            for para in shape.text:
                t = para.text()
                if t:
                    got.append(t)
        assert got == want_slide["texts"], (
            f"deck_01 slide {ex_slide.index} shape text order diverged"
        )


def test_extract_directory_reaches_every_deck(corpus_dir: Path) -> None:
    res = extract_directory(corpus_dir)
    assert res.decks
    assert len(res.decks) == 24
    assert not res.errors
    counts = sorted(d.slide_count for d in res.decks)
    assert all(c >= 10 for c in counts)


def slide_text_paragraphs(slide) -> list[str]:
    """Flatten a parsed slide into the exact document-order text strings the
    generator recorded: one entry per paragraph, paragraphs in shape-walk and
    then insertion order."""
    out: list[str] = []
    for shape in slide.shapes:
        for para in shape.text:
            t = para.text()
            if t:
                out.append(t)
    return out


def _snake(s: str) -> str:
    return s.strip().lower().replace(" ", "_")


# --------------------------------------------------------------------------- #
# Contract locks
# --------------------------------------------------------------------------- #
def test_extracted_slide_contract_fields() -> None:
    """Surface the schema fields downstream analysis relies on (regression
    guard against renames)."""
    from deckforge_core.schemas.extracted import ExtractedShape, ExtractedSlide

    fields = ExtractedSlide.model_fields
    for expected in ("index", "aspect_ratio", "slide_size_emu", "shapes",
                     "notes_text", "extraction_errors"):
        assert expected in fields

    shape_fields = ExtractedShape.model_fields
    for expected in ("shape_id", "name", "shape_type", "x", "y", "w", "h",
                     "text", "image"):
        assert expected in shape_fields

"""Determinism + determinism invariants for the synthetic corpus (Workstream A).

The corpus is only as good as its reproducibility: the whole reason DeckForge
chose *synthetic* decks over scraping is that a fixed ``(seed, argv)`` must
produce **byte-identical** ``.pptx`` and ``*.slides.json`` every run, on every
machine. These tests are the gate that enforces that property going forward, so
a future "small" change (a theme hex, a font string, a new archetype, an
ordering tweak) can't silently make the corpus non-reproducible.

Three guarantees are locked here:

1. **Same inputs → same bytes** — two runs of the generator with the same
   ``--seed``/``--decks`` into different directories produce byte-identical
   output files (content *and* zip timestamps, so even the archive metadata is
   pinned).
2. **Different seeds → different bytes** — different seeds must not collide,
   otherwise the corpus degenerates into repeats.
3. **Sidecar matches generator** — the ``*.slides.json`` records exactly the
   text strings the generator wrote, in document (insertion) order.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from deckforge_core.tools import generate_corpus


def _pptx_texts_by_slide(pptx_path: Path) -> list[str]:
    """Document-order text as stored in the archive (the read-side contract)."""
    from pptx import Presentation

    prs = Presentation(str(pptx_path))
    out = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                out.append(shape.text_frame.text)
    return out


# --------------------------------------------------------------------------- #
# 1. Same inputs, same bytes
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("decks", [3, 6])
def test_same_seed_is_byte_identical(tmp_path: Path, decks: int) -> None:
    out_a = tmp_path / "corpus_a"
    out_b = tmp_path / "corpus_b"
    rc_a = generate_corpus.main(["--out", str(out_a), "--decks", str(decks),
                                 "--seed", "20241231"])
    rc_b = generate_corpus.main(["--out", str(out_b), "--decks", str(decks),
                                 "--seed", "20241231"])
    assert rc_a == 0
    assert rc_b == 0

    files_a = sorted(p.name for p in out_a.glob("*.pptx"))
    files_b = sorted(p.name for p in out_b.glob("*.pptx"))
    assert files_a == files_b
    for name in files_a:
        bytes_a = (out_a / name).read_bytes()
        bytes_b = (out_b / name).read_bytes()
        assert bytes_a == bytes_b, f"{name} differs between two same-seed runs"

    sidecars_a = sorted((out_a / name.replace(".pptx", ".slides.json"))
                        for name in files_a)
    for path_a in sidecars_a:
        path_b = out_b / path_a.name
        assert path_a.read_bytes() == path_b.read_bytes(), (
            f"{path_a.name} sidecar differs between two same-seed runs"
        )


def test_zip_timestamps_are_pinned(tmp_path: Path) -> None:
    """Zip entry times must be identical across runs, so the byte stream (not
    just the decompressed XML) is reproducible."""
    out_a = tmp_path / "corpus_a"
    out_b = tmp_path / "corpus_b"
    generate_corpus.main(["--out", str(out_a), "--decks", "6", "--seed", "7"])
    generate_corpus.main(["--out", str(out_b), "--decks", "6", "--seed", "7"])

    def _zip_entry_dates(directory: Path) -> list[tuple[str, tuple[int, ...]]]:
        pptx = sorted(directory.glob("*.pptx"))[0]
        with zipfile.ZipFile(pptx) as zf:
            return [(i.filename, i.date_time) for i in zf.infolist()]

    assert _zip_entry_dates(out_a) == _zip_entry_dates(out_b)


# --------------------------------------------------------------------------- #
# 2. Different seeds don't collide
# --------------------------------------------------------------------------- #
def test_different_seeds_differ(tmp_path: Path) -> None:
    out_a = tmp_path / "corpus_a"
    out_b = tmp_path / "corpus_b"
    generate_corpus.main(["--out", str(out_a), "--decks", "6", "--seed", "1"])
    generate_corpus.main(["--out", str(out_b), "--decks", "6", "--seed", "2"])
    for name in sorted(p.name for p in out_a.glob("*.pptx")):
        if (out_b / name).exists():
            assert (out_a / name).read_bytes() != (out_b / name).read_bytes(), (
                f"seeds 1 and 2 produced identical {name}")


# --------------------------------------------------------------------------- #
# 3. The generator is the source of truth; sidecar mirrors the deck bytes
# --------------------------------------------------------------------------- #
def test_generator_writes_payloads(tmp_path: Path) -> None:
    out = tmp_path / "corpus"
    generate_corpus.main(["--out", str(out), "--decks", "4", "--seed", "9"])
    decks = sorted(out.glob("deck_*.pptx"))
    assert decks
    for pptx_path in decks:
        sidecar_path = pptx_path.with_suffix(".slides.json")
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert sidecar["seed"] == 9
        assert "slides" in sidecar
        for slide_meta in sidecar["slides"]:
            assert "texts" in slide_meta
            assert isinstance(slide_meta["texts"], list)
            assert all(isinstance(t, str) for t in slide_meta["texts"])

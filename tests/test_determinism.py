"""Determinism gate for the synthetic corpus generator (Workstream A).

The generator is only useful for ingest regression testing if it is
*reproducible*: the same ``(seed, argv)`` must always produce byte-identical
``.pptx`` files and byte-identical ``.slides.json`` sidecars, on any machine and
any run.

What "byte-identical" covers
---------------------------
* The whole ``.pptx`` archive contents (text, geometry, notes, charts, tables,
  connectors, embedded PNGs) — checked via the SHA-256 of the raw bytes AND
  per-entry zip metadata so a stray wall-clock timestamp can never slip in.
* The sidecar JSON, deterministically serialised, same field order both runs.

If either build is ever found be non-reproducible this test fails loudly so a
team fixes the generator instead of discovering drift later in the pipeline.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from deckforge_core.ingest import deck_hash
from deckforge_core.tools import generate_corpus as gc


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pptx_entry_table(path: Path) -> dict[str, tuple]:
    """Map of filename -> (date_time, file_size) pulled from the zip every
    build MUST carry. Exists so the test can prove not just the decompressed
    bytes but the archive metadata itself is pinned/deterministic."""
    entries: dict[str, tuple] = {}
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            entries[info.filename] = (info.date_time, info.file_size)
    return entries


@pytest.fixture
def out_dirs(tmp_path: Path) -> tuple[Path, Path]:
    """Two sibling output directories that must end up byte-identical."""
    a = tmp_path / "corpus_a"
    b = tmp_path / "corpus_b"
    a.mkdir()
    b.mkdir()
    return a, b


# --------------------------------------------------------------------------- #
# Determinism: two runs of the same seed must be byte-identical
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("decks", [2, 4])
def test_same_seed_is_byte_identical(tmp_path: Path, decks: int) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    seed = 20240316
    rc_a = gc.main(["--out", str(a), "--decks", str(decks), "--seed", str(seed)])
    rc_b = gc.main(["--out", str(b), "--decks", str(decks), "--seed", str(seed)])
    assert rc_a == rc_b == 0

    for path_a, path_b in zip(sorted(a.glob("deck_*.pptx")),
                              sorted(b.glob("deck_*.pptx"))):
        assert path_a.name == path_b.name
        assert path_a.read_bytes() == path_b.read_bytes(), (
            f"{path_a.name} differs between identical seeds")
        assert _pptx_entry_table(path_a) == _pptx_entry_table(path_b), (
            f"zip metadata differs for {path_a.name}")

    for side_a, side_b in zip(sorted(a.glob("deck_*.slides.json")),
                              sorted(b.glob("deck_*.slides.json"))):
        assert side_a.name == side_b.name
        assert side_a.read_text(encoding="utf-8") == side_b.read_text(
            encoding="utf-8")


def test_corpus_engine_is_reproducible_across_processes(
    tmp_path: Path, out_dirs: tuple[Path, Path]
) -> None:
    """Same seed built by two separate interpreter invocations must land on the
    same bytes — this is the real test that wall-clock/entropy never leaks in."""
    a, b = out_dirs
    base = [sys.executable, "-m", "deckforge_core.tools.generate_corpus"]
    common = ["--decks", "3", "--seed", "42"]
    subprocess.run(base + ["--out", str(a)] + common, check=True,
                   capture_output=True, text=True)
    subprocess.run(base + ["--out", str(b)] + common, check=True,
                   capture_output=True, text=True)
    for path_a, path_b in zip(sorted(a.glob("deck_*.pptx")),
                              sorted(b.glob("deck_*.pptx"))):
        assert path_a.name == path_b.name
        assert path_a.read_bytes() == path_b.read_bytes()


def test_seed_changes_bytes(tmp_path: Path, out_dirs: tuple[Path, Path]) -> None:
    """Different seeds must NOT collide — otherwise the corpus is degenerate."""
    a, b = out_dirs
    gc.main(["--out", str(a), "--decks", "6", "--seed", "1"])
    gc.main(["--out", str(b), "--decks", "6", "--seed", "2"])
    names = sorted(x.name for x in a.glob("deck_*.pptx"))
    assert names
    for name in names:
        assert (a / name).read_bytes() != (b / name).read_bytes(), (
            f"seeds 1 vs 2 produced identical {name}")


def test_deck_hash_is_stable_and_unique(
    tmp_path: Path, out_dirs: tuple[Path, Path]
) -> None:
    """The ingest-side content key must be (a) stable across runs of the same
    file and (b) distinct across decks, so caching has a sound key."""
    a, b = out_dirs
    gc.main(["--out", str(a), "--decks", "3", "--seed", "7"])
    gc.main(["--out", str(b), "--decks", "3", "--seed", "7"])

    a_decks = sorted(a.glob("deck_*.pptx"))
    b_decks = sorted(b.glob("deck_*.pptx"))
    assert a_decks and len(a_decks) == len(b_decks)
    for pa, pb in zip(a_decks, b_decks):
        ha, hb = deck_hash(pa), deck_hash(pb)
        assert ha == hb, f"deck_hash not stable across runs for {pa.name}"
        assert ha == deck_hash(pa), f"deck_hash not idempotent for {pa.name}"

    hashes = [deck_hash(p) for p in a_decks]
    assert len(set(hashes)) == len(hashes), "deck_hash collided across decks"


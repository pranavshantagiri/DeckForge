"""Parallel ingest (batch) tests: determinism + parity with the serial path."""

from __future__ import annotations

import pytest

from deckforge_core.ingest.batch import (
    effective_workers,
    extract_directory_parallel,
)
from deckforge_core.ingest.parser import extract_directory
from deckforge_core.tools.generate_corpus import build_deck


@pytest.fixture()
def corpus(tmp_path):
    out = tmp_path / "corpus"
    out.mkdir()
    for i in range(8):
        build_deck(out / f"deck_{i:02d}.pptx", i, seed=20240316)
    return out


def test_effective_workers_logic():
    assert effective_workers(None, 10) == 1
    assert effective_workers(1, 10) == 1
    assert effective_workers(0, 10) == 2  # auto, but capped by corpus size
    assert effective_workers(4, 2) == 2  # never more than files
    assert effective_workers(0, 0) == 1


def test_parallel_matches_serial(corpus):
    serial = extract_directory(corpus, use_cache=False)
    parallel = extract_directory_parallel(corpus, workers=0, use_cache=False)

    assert parallel.new_parses == serial.new_parses == 8
    assert [d.path for d in parallel.decks] == [d.path for d in serial.decks]
    assert len(parallel.errors) == len(serial.errors)
    for a, b in zip(parallel.decks, serial.decks):
        assert a.model_dump_json() == b.model_dump_json()


def test_parallel_is_deterministic(corpus):
    first = extract_directory_parallel(corpus, workers=0, use_cache=False)
    second = extract_directory_parallel(corpus, workers=0, use_cache=False)
    assert [d.path for d in first.decks] == [d.path for d in second.decks]
    assert [(d.path, d.slide_count) for d in first.decks] == [
        (d.path, d.slide_count) for d in second.decks
    ]
    assert first.new_parses == second.new_parses == 8


def test_parallel_cache_writes_once_and_is_shared(corpus, tmp_path):
    db = tmp_path / "cache.db"
    parallel = extract_directory_parallel(
        corpus, workers=0, use_cache=True, db_path=db
    )
    assert parallel.new_parses == 8
    second = extract_directory(corpus, use_cache=True, db_path=db)
    assert second.cached_hits == 8


def test_parallel_single_worker_falls_back(corpus):
    result = extract_directory_parallel(corpus, workers=1, use_cache=False)
    assert result.new_parses == 8  # falls back to the serial path

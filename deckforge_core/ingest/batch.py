"""Parallel .pptx ingestion for large corpora (Phase 3 performance).

``extract_directory_parallel`` walks a folder exactly like the serial
:func:`deckforge_core.ingest.parser.extract_directory` but parses decompressed /
unparsed decks across a ``ProcessPoolExecutor``. Determinism is preserved:

* files are processed in sorted order;
* output order matches file order regardless of which worker finished first;
* cache hits are served in-place (hashes are computed up front, serially);
* the SQLite cache is written only from the parent process.

Only the CPU-bound ``extract_deck`` work goes to workers; everything stateful
(cache, ordering, result bookkeeping) stays single-threaded.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Callable, Optional, Tuple

from deckforge_core.ingest.cache import IngestCache, deck_hash
from deckforge_core.ingest.parser import (
    IngestError,
    IngestResult,
    extract_deck,
)
from deckforge_core.logging_util import get_logger
from deckforge_core.schemas.extracted import ExtractedDeck

log = get_logger("deckforge.ingest.batch")


def _discover_pptx(folder: Path) -> list[Path]:
    return sorted(
        {p for p in folder.glob("*.pptx")} | {p for p in folder.glob("**/*.pptx")}
    )


def _extract_one(path: str) -> Tuple[Optional[ExtractedDeck], Optional[str]]:
    """Top-level worker: parse one deck, never raises across the pipe."""
    try:
        return extract_deck(Path(path)), None
    except Exception as exc:  # InvalidDeckError and any unexpected parse failure
        return None, str(exc)


def effective_workers(workers: Optional[int], file_count: int) -> int:
    """Resolve a ``workers`` request to an actual pool size.

    ``None``/``1`` -> serial (no pool). ``0`` -> auto: CPU count capped so that
    each worker gets roughly ``file_count / workers >= 4`` files, which keeps
    subprocess spawn overhead amortized on small corpora (a 16-worker pool
    spawn takes seconds but only pays off at hundreds of decks). ``>1`` -> that
    many (still capped by file count).
    """
    if workers is None or workers == 1 or file_count <= 1:
        return 1
    if workers > 0:
        return min(workers, file_count)
    candidate = min(os.cpu_count() or 1, file_count)
    while candidate > 1 and file_count < candidate * 4:
        candidate //= 2
    return max(1, candidate)


def extract_directory_parallel(
    folder: Path,
    *,
    workers: int = 0,
    use_cache: bool = True,
    on_progress: Optional[Callable[[Path], None]] = None,
    db_path: Optional[Path] = None,
) -> IngestResult:
    """Parallel equivalent of :func:`extract_directory` (deterministic)."""
    folder = Path(folder)
    files = _discover_pptx(folder)
    pool_size = effective_workers(workers, len(files))
    if pool_size <= 1:
        from deckforge_core.ingest.parser import extract_directory

        return extract_directory(
            folder, use_cache=use_cache, on_progress=on_progress, db_path=db_path
        )

    result = IngestResult()
    cache = IngestCache(db_path) if use_cache else None
    pending: list[tuple[int, Path, str]] = []  # (index, path, file_hash)
    try:
        for index, path in enumerate(files):
            try:
                file_hash = deck_hash(path)
            except OSError as exc:
                result.errors.append(IngestError(path, f"unreadable file: {exc}"))
                continue
            if cache is not None:
                cached = cache.get(file_hash)
                if cached is not None:
                    result.cached_hits += 1
                    _place(result, index, cached)
                    continue
            pending.append((index, path, file_hash))
            _place(result, index, None)  # reserve the slot, filled after parse

        if pending and pool_size > 1:
            with ProcessPoolExecutor(max_workers=pool_size) as pool:
                outcomes = pool.map(
                    _extract_one, [str(path) for _, path, _ in pending]
                )
                for (index, path, file_hash), (deck, error) in zip(pending, outcomes):
                    if on_progress is not None:
                        on_progress(path)
                    if deck is None or error:
                        result.errors.append(IngestError(path, error or "unknown parse failure"))
                        if cache is not None:
                            cache.record_error(str(path), error or "unknown parse failure")
                        continue
                    result.new_parses += 1
                    if cache is not None:
                        cache.put(file_hash, deck)
                    _place(result, index, deck)
    finally:
        if cache is not None:
            cache.close()
    result.decks = [d for d in result.decks if d is not None]
    return result


def _place(result: IngestResult, index: int, deck: Optional[ExtractedDeck]) -> None:
    """Insert ``deck`` at ``index`` in a sparse list used to keep file order."""
    while len(result.decks) <= index:
        result.decks.append(None)
    result.decks[index] = deck

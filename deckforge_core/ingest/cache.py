"""Ingest cache: sha256-keyed metadata + extracted-deck payloads.

The SQLite ``ingest_cache``/``decks``/``ingest_errors`` tables are written
through :class:`deckforge_core.storage.sqlite.Database`. Because the frozen DB
schema has no payload column, the full extracted deck is stored as JSON next
to the database (``<db_dir>/<dbname>_extracted/<hash>.json``); the DB row is
the authoritative "have we seen this file" marker (``deck_by_hash``).

Any DB failure (busy, locked, corrupt schema) degrades to a no-cache mode with
a warning log — extraction still works, it just re-parses every file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional

from deckforge_core.config import ensure_dirs
from deckforge_core.logging_util import get_logger
from deckforge_core.schemas.extracted import ExtractedDeck
from deckforge_core.storage.sqlite import Database

log = get_logger("deckforge.ingest.cache")

_HASH_CHUNK = 1024 * 1024


def deck_hash(path: Path) -> str:
    """sha256 of the raw .pptx bytes on disk."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(_HASH_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _payload_dir(db_path: Optional[Path]) -> Path:
    """Directory for extracted-deck JSON payloads, tied to the db location
    so tests that pass a tmp db path keep all state inside tmp."""
    if db_path is not None:
        target = db_path.parent / f"{db_path.stem}_extracted"
    else:
        target = ensure_dirs()["cache"] / "extracted"
    target.mkdir(parents=True, exist_ok=True)
    return target


class IngestCache:
    """Hash-keyed cache used by :func:`extract_directory`.

    ``db_path=None`` uses the default DeckForge metadata database under
    ``%APPDATA%\\DeckForge``.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path
        self._dir: Optional[Path] = None
        try:
            self._db = Database(db_path) if db_path is not None else Database()
            self._dir = _payload_dir(db_path)
            self._ok = True
        except Exception as exc:  # pragma: no cover - environment dependent
            log.warning("ingest cache unavailable (%s); falling back to no-cache", exc)
            self._db = None
            self._ok = False

    @property
    def available(self) -> bool:
        return self._ok

    def get(self, file_hash: str) -> Optional[ExtractedDeck]:
        """Return the cached deck for ``file_hash`` or None (cache miss).

        A hit requires both the DB marker row and a readable JSON payload; a
        missing/corrupt payload is treated as a miss so the caller re-parses.
        """
        if not self._ok or self._dir is None:
            return None
        try:
            row = self._db.deck_by_hash(file_hash)
            if row is None:
                return None
            payload = self._dir / f"{file_hash}.json"
            if not payload.exists():
                return None
            data = json.loads(payload.read_text(encoding="utf-8"))
            deck = ExtractedDeck.model_validate(data["deck"])
            if deck.path and Path(deck.path).exists():
                return deck
            return None
        except Exception as exc:
            log.warning("cache read failed for %s: %s (treating as miss)", file_hash, exc)
            return None

    def put(self, file_hash: str, deck: ExtractedDeck) -> None:
        """Record a successfully parsed deck under its hash."""
        if not self._ok or self._dir is None:
            return
        try:
            deck_id = f"df-{file_hash[:20]}"
            self._db.record_deck(deck_id, str(deck.path), file_hash, deck.slide_count)
            # ingest_cache is authoritative "indexed" marker; decks.UNIQUE(file_hash)
            # keeps the decks table one row per file.
            self._db._conn.execute(
                "INSERT OR REPLACE INTO ingest_cache (file_hash, deck_id, ok, slides, indexed_at)"
                " VALUES (?, ?, 1, ?, datetime('now'))",
                (file_hash, deck_id, deck.slide_count),
            )
            self._db._conn.commit()
            payload = self._dir / f"{file_hash}.json"
            record = {"hash": file_hash, "deck": deck.model_dump(mode="json")}
            payload.write_text(
                json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as exc:
            log.warning("cache write failed for %s: %s (continuing without cache)", file_hash, exc)
            self._ok = False  # a failing DB is not going to get better mid-run
            self._db = None
            self._dir = None

    def record_error(self, path: str, message: str) -> None:
        try:
            if self._ok:
                self._db.record_ingest_error(path, message)
        except Exception as exc:
            log.warning("could not record ingest error for %s: %s", path, exc)
            self._ok = False
            self._db = None

    def close(self) -> None:
        if self._ok:
            try:
                self._db.close()
            except Exception:  # pragma: no cover
                pass

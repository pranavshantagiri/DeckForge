"""Local metadata storage (SQLite)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from deckforge_core.config import ensure_dirs
from deckforge_core.errors import StorageError
from deckforge_core.logging_util import get_logger

log = get_logger("deckforge.storage")

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS packs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    path TEXT NOT NULL,
    source_deck_count INTEGER DEFAULT 0,
    created_at TEXT,
    archetypes TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS decks (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    slide_count INTEGER DEFAULT 0,
    source_pack TEXT,
    ingested_at TEXT,
    UNIQUE(file_hash)
);

CREATE TABLE IF NOT EXISTS ingest_cache (
    file_hash TEXT PRIMARY KEY,
    deck_id TEXT,
    ok INTEGER NOT NULL DEFAULT 1,
    error TEXT,
    slides INTEGER DEFAULT 0,
    indexed_at TEXT
);

CREATE TABLE IF NOT EXISTS ingest_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    error TEXT NOT NULL,
    recorded_at TEXT
);

CREATE TABLE IF NOT EXISTS llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,
    job TEXT,
    recorded_at TEXT
);

CREATE TABLE IF NOT EXISTS generated_decks (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    prompt TEXT,
    pack TEXT,
    plan_json TEXT,
    qa_json TEXT,
    created_at TEXT
);
"""


class Database:
    """Thin wrapper around the DeckForge SQLite metadata database."""

    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            db_path = ensure_dirs()["db"] / "deckforge.db"
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        try:
            self._conn.executescript(SCHEMA)
            self._conn.commit()
        except sqlite3.Error as exc:  # pragma: no cover
            raise StorageError(f"DB migration failed: {exc}") from exc

    # ---- conveniences used across workstreams ----
    def record_deck(self, deck_id: str, path: str, file_hash: str, slide_count: int,
                    source_pack: str | None = None) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO decks (id, path, file_hash, slide_count, source_pack, ingested_at)"
            " VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (deck_id, path, file_hash, slide_count, source_pack),
        )
        self._conn.commit()

    def deck_by_hash(self, file_hash: str) -> sqlite3.Row | None:
        cur = self._conn.execute(
            "SELECT * FROM decks WHERE file_hash = ?", (file_hash,)
        )
        return cur.fetchone()

    def record_ingest_error(self, path: str, error: str) -> None:
        self._conn.execute(
            "INSERT INTO ingest_errors (path, error, recorded_at) VALUES (?, ?, datetime('now'))",
            (path, error),
        )
        self._conn.commit()

    def record_usage(self, provider: str, model: str, input_tokens: int,
                     output_tokens: int, cache_read_tokens: int, cost_usd: float,
                     job: str | None = None) -> int:
        cur = self._conn.execute(
            "INSERT INTO llm_usage (provider, model, input_tokens, output_tokens,"
            " cache_read_tokens, cost_usd, job, recorded_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            (provider, model, input_tokens, output_tokens, cache_read_tokens, cost_usd, job),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def total_usage(self) -> tuple[int, int, float]:
        """Return (input_tokens, output_tokens, cost_usd) summed across all LLM calls."""
        cur = self._conn.execute(
            "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0),"
            " COALESCE(SUM(cost_usd),0) FROM llm_usage"
        )
        row = cur.fetchone()
        return (int(row[0]), int(row[1]), float(row[2]))

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

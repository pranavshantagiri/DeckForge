"""Storage tests (SQLite metadata layer)."""

from __future__ import annotations

from deckforge_core.storage import Database


def test_db_schema_creates(tmp_workspace):
    db = Database(tmp_workspace / "t.db")
    try:
        db.record_deck("d1", "C:\\decks\\a.pptx", "hash1", 12, source_pack="demo")
        assert db.deck_by_hash("hash1")["slide_count"] == 12
        db.record_usage("anthropic", "claude-sonnet-5", 100, 20, 0, 0.001, "test")
        inp, outp, cost = db.total_usage()
        assert inp == 100 and outp == 20 and cost == pytest.approx(0.001)
    finally:
        db.close()


import pytest  # noqa: E402

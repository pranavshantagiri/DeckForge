"""Storage: SQLite metadata + (later) local vector index. No cloud anywhere."""

from deckforge_core.storage.sqlite import Database, StorageError  # noqa: F401

__all__ = ["Database"]

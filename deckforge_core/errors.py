"""Shared exception hierarchy for DeckForge.

Every error raised by core code derives from :class:`DeckForgeError` so that
interfaces (CLI/GUI) can catch one type and degrade gracefully instead of
showing stack traces.
"""

from __future__ import annotations


class DeckForgeError(Exception):
    """Base class for all DeckForge errors."""


class ConfigError(DeckForgeError):
    """Invalid or missing configuration."""


class PackError(DeckForgeError):
    """Something is wrong with a Format Pack on disk."""


class PackNotFoundError(PackError):
    """The requested pack does not exist."""


class PackCorruptError(PackError):
    """The pack exists but its files fail validation."""


class InvalidDeckError(DeckForgeError):
    """A .pptx could not be parsed or is unusable."""


class ProviderError(DeckForgeError):
    """Base class for failures inside a provider."""


class LLMError(ProviderError):
    """LLM call failed."""


class ImageError(ProviderError):
    """Image fetch/search failed."""


class RendererError(DeckForgeError):
    """Slide rendering to images failed."""


class StorageError(DeckForgeError):
    """SQLite / vector store failure."""


class LocalOnlyError(DeckForgeError):
    """A cloud operation was attempted while in local-only mode.

    Raised instead of silently contacting a network API when the user (or a
    pack) has opted in to local-only processing.
    """

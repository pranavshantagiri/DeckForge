"""Attribution strings for image credits and captions."""

from __future__ import annotations

from deckforge_core.providers.images import ImageItem

_FALLBACK = "Photo provided by DeckForge"

DEFAULT_LICENSES: dict[str, str] = {
    "unsplash": "Unsplash license",
    "pexels": "Pexels license",
    "local": "local",
}


def attribution_footer(item: ImageItem) -> str:
    """Footer line crediting the photographer.
    Returns the provider-supplied attribution; falls back for blank entries."""
    return item.attribution or _FALLBACK


def caption_line(item: ImageItem) -> str:
    """Single-line caption under a placed image."""
    return item.attribution or _FALLBACK


def license_note(item: ImageItem) -> str:
    """Human-readable licence for the item, resolving provider defaults."""
    return item.license or DEFAULT_LICENSES.get(item.provider, item.provider)

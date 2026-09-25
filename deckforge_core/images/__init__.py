"""Image acquisition, ranking, attribution and the local photo library.

Workstream E: sources are iterated in configured order (settings
``image_sources``) with deduplication, results are quality-filtered/ranked
offline, fetched photos are cached under ``cache_dir/<provider>/``.
"""

from __future__ import annotations

import re
from pathlib import Path
from shutil import copyfile
from urllib.parse import unquote, urlparse

from deckforge_core.config import Settings, data_dir
from deckforge_core.errors import ImageError
from deckforge_core.images.attribution import (
    attribution_footer,
    caption_line,
    license_note,
)
from deckforge_core.images.local_library import LocalPhotoLibrary, dhash
from deckforge_core.images.providers import PexelsProvider, UnsplashProvider
from deckforge_core.images.rank import (
    QualityFilter,
    has_acceptable_aspect,
    is_large_enough,
    looks_watermarked,
    pick_best,
    rank_results,
)
from deckforge_core.images.registry_bootstrap import (
    bootstrap_image_providers,
    image_provider_for,
)
from deckforge_core.logging_util import get_logger
from deckforge_core.providers.images import ImageItem

log = get_logger("deckforge.images")

_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def _ext_for(url: str) -> str:
    ext = Path(urlparse(url).path).suffix.lower()
    if ext in _ALLOWED_EXTS:
        return ext.lstrip(".")
    return "jpg"


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return cleaned or "image"


def _file_url_to_path(url: str) -> Path:
    stripped = url[len("file://") :] if url.startswith("file://") else url
    if stripped.startswith("/") and len(stripped) > 2 and stripped[2] == ":":
        stripped = stripped[1:]
    return Path(unquote(stripped))


def _local_photos_root(local_root: str | Path | None) -> Path:
    if local_root is not None:
        return Path(local_root)
    return data_dir() / "photos"


def _search_source(
    source: str,
    query: str,
    *,
    limit: int,
    min_w: int,
    min_h: int,
    orientation: str,
    local_root: str | Path | None,
) -> list[ImageItem]:
    if source == "local":
        library = LocalPhotoLibrary(_local_photos_root(local_root))
        candidates = [
            item
            for item in library.search(query, limit=max(limit * 4, limit))
            if is_large_enough(item, min_w, min_h)
        ]
        return candidates[:limit]
    provider = image_provider_for(source)
    return provider.search(
        query,
        limit=limit,
        min_width=min_w,
        min_height=min_h,
        orientation=orientation,
    )


def search_images(
    sources: list[str] | None = None,
    query: str = "",
    *,
    limit: int = 8,
    min_w: int = 800,
    min_h: int = 600,
    orientation: str = "landscape",
    local_root: str | Path | None = None,
) -> list[ImageItem]:
    """Search configured photo sources in order, deduped by attribution+url.

    ``sources`` defaults to the settings key ``image_sources``. A source that
    fails (e.g. a provider with no API key) is logged and skipped; the others
    still contribute.
    """
    if sources is None:
        sources = Settings().get("image_sources", ["unsplash", "pexels", "local"])
    seen: set[tuple[str, str]] = set()
    results: list[ImageItem] = []
    for source in sources:
        try:
            items = _search_source(
                source,
                query,
                limit=limit,
                min_w=min_w,
                min_h=min_h,
                orientation=orientation,
                local_root=local_root,
            )
        except (ImageError, ValueError) as exc:
            log.warning("image source %r skipped: %s", source, exc)
            continue
        for item in items:
            key = (item.attribution, item.url)
            if key not in seen:
                seen.add(key)
                results.append(item)
    return results


def fetch_and_store(item: ImageItem, cache_dir: Path | str) -> Path:
    """Fetch ``item`` into ``cache_dir/<provider>/<id>.<ext>`` (deduped).

    Local-library items are copied from their file URL; remote items are
    downloaded through the item's provider. Returns the destination path.
    """
    cache_dir = Path(cache_dir)
    dest = cache_dir / item.provider / f"{_safe_id(item.id)}.{_ext_for(item.url)}"
    if dest.exists():
        return dest
    if item.provider == "local":
        src = _file_url_to_path(item.url)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            copyfile(src, dest)
        except OSError as exc:
            raise ImageError(f"local image {src} could not be cached: {exc}") from exc
        return dest
    provider = image_provider_for(item.provider)
    return provider.fetch(item, dest)


def local_photos(root: Path | str) -> LocalPhotoLibrary:
    """Build a :class:`LocalPhotoLibrary` indexed from ``root``."""
    return LocalPhotoLibrary(root)


__all__ = [
    "ImageItem",
    "LocalPhotoLibrary",
    "PexelsProvider",
    "QualityFilter",
    "UnsplashProvider",
    "attribution_footer",
    "bootstrap_image_providers",
    "caption_line",
    "dhash",
    "fetch_and_store",
    "has_acceptable_aspect",
    "image_provider_for",
    "is_large_enough",
    "license_note",
    "local_photos",
    "looks_watermarked",
    "pick_best",
    "rank_results",
    "search_images",
]

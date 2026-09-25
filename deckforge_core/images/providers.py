"""Real-photo providers: Unsplash and Pexels.

Both providers implement :class:`ImageProvider` and are thin REST clients.
Transport is injectable (``session``) so tests run with a stub and never touch
the network. API keys are resolved via :class:`SecretStore` at construction,
which keeps provider creation cheap and failure-free when no key is set; the
error surfaces only when ``search`` is actually called.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from deckforge_core.config import SecretStore
from deckforge_core.errors import ImageError
from deckforge_core.logging_util import get_logger
from deckforge_core.providers.base import Capability
from deckforge_core.providers.images import ImageItem, ImageProvider

log = get_logger("deckforge.images.providers")

_REQUEST_TIMEOUT = 30


def _make_urls(candidate: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = candidate.get(key)
        if value:
            return value
    return ""


class UnsplashProvider(ImageProvider):
    """Images from https://unsplash.com/developers (requires an API key)."""

    name = "unsplash"
    capabilities = {Capability.IMAGE_SEARCH, Capability.IMAGE_FETCH}

    ENDPOINT = "https://api.unsplash.com/search/photos"
    _KEY_NAME = "unsplash"

    def __init__(
        self, api_key: str | None = None, session: requests.Session | None = None
    ) -> None:
        self._api_key = api_key if api_key is not None else SecretStore().get(self._KEY_NAME)
        self._session = session if session is not None else requests.Session()

    def healthcheck(self) -> str:
        status = "key configured" if self._api_key else "no key"
        return f"unsplash ({status})"

    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        min_width: int = 800,
        min_height: int = 600,
        orientation: str = "landscape",
    ) -> list[ImageItem]:
        if not self._api_key:
            raise ImageError(
                "unsplash search requires an API key (SecretStore 'unsplash')"
            )
        params: dict[str, Any] = {"query": query, "per_page": limit}
        if orientation:
            params["orientation"] = orientation
        data = self._get_json(
            self.ENDPOINT, params=params, headers={"Authorization": f"Client-ID {self._api_key}"}
        )
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            raise ImageError("unsplash search returned no result list")
        items: list[ImageItem] = []
        for raw in results:
            if not isinstance(raw, dict):
                continue
            try:
                item = self._map_result(raw)
            except (KeyError, TypeError, ValueError) as exc:
                log.warning("unsplash: skipped malformed result: %s", exc)
                continue
            if item.width < min_width or item.height < min_height:
                continue
            items.append(item)
            if len(items) >= limit:
                break
        return items

    def _map_result(self, raw: dict[str, Any]) -> ImageItem:
        urls = raw["urls"] or {}
        user = raw["user"] or {}
        links = raw["links"] or {}
        photographer = user.get("name", "") or ""
        return ImageItem(
            id=str(raw["id"]),
            provider=self.name,
            url=_make_urls(urls, ("regular", "raw", "full")),
            thumb_url=_make_urls(urls, ("thumb", "small")),
            width=int(raw["width"]),
            height=int(raw["height"]),
            license="Unsplash license",
            attribution=f"Photo by {photographer} on Unsplash",
            page_url=links.get("html", "") or "",
            alt=raw.get("alt_description", "") or raw.get("description", "") or "",
            color=raw.get("color", "") or "",
        )

    def fetch(self, item: ImageItem, dest: Path) -> Path:
        return self._download(item, dest)

    def _get_json(self, url: str, *, params: dict, headers: dict) -> dict[str, Any]:
        try:
            response = self._session.get(url, params=params, headers=headers, timeout=_REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ImageError(f"{self.name} request failed: {exc}") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise ImageError(f"{self.name} returned invalid JSON") from exc
        return data

    def _download(self, item: ImageItem, dest: Path) -> Path:
        dest = Path(dest)
        try:
            response = self._session.get(item.url, timeout=_REQUEST_TIMEOUT)
            response.raise_for_status()
            content = bytes(response.content)
        except requests.RequestException as exc:
            raise ImageError(f"{self.name} fetch failed for {item.id}: {exc}") from exc
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
        except OSError as exc:
            raise ImageError(f"{self.name} could not write {dest}: {exc}") from exc
        return dest


class PexelsProvider(UnsplashProvider):
    """Images from https://www.pexels.com/api/ (requires an API key)."""

    name = "pexels"
    ENDPOINT = "https://api.pexels.com/v1/search"
    _KEY_NAME = "pexels"

    def __init__(
        self, api_key: str | None = None, session: requests.Session | None = None
    ) -> None:
        super().__init__(api_key=api_key, session=session)

    def healthcheck(self) -> str:
        status = "key configured" if self._api_key else "no key"
        return f"pexels ({status})"

    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        min_width: int = 800,
        min_height: int = 600,
        orientation: str = "landscape",
    ) -> list[ImageItem]:
        if not self._api_key:
            raise ImageError("pexels search requires an API key (SecretStore 'pexels')")
        params: dict[str, Any] = {"query": query, "per_page": limit}
        if orientation:
            params["orientation"] = orientation
        data = self._get_json(
            self.ENDPOINT, params=params, headers={"Authorization": self._api_key}
        )
        photos = data.get("photos") if isinstance(data, dict) else None
        if not isinstance(photos, list):
            raise ImageError("pexels search returned no photo list")
        items: list[ImageItem] = []
        for raw in photos:
            if not isinstance(raw, dict):
                continue
            try:
                item = self._map_result(raw)
            except (KeyError, TypeError, ValueError) as exc:
                log.warning("pexels: skipped malformed result: %s", exc)
                continue
            if item.width < min_width or item.height < min_height:
                continue
            items.append(item)
            if len(items) >= limit:
                break
        return items

    def _map_result(self, raw: dict[str, Any]) -> ImageItem:
        src = raw.get("src") or {}
        return ImageItem(
            id=str(raw["id"]),
            provider=self.name,
            url=_make_urls(src, ("original", "large2x", "large")),
            thumb_url=_make_urls(src, ("medium", "small")),
            width=int(raw["width"]),
            height=int(raw["height"]),
            license="Pexels license",
            attribution=f"Photo by {raw.get('photographer', '') or ''} on Pexels",
            page_url=raw.get("url", "") or "",
            alt=raw.get("alt", "") or "",
            color=raw.get("avg_color", "") or "",
        )

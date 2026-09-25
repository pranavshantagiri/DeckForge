"""Provider tests: Unsplash + Pexels mapping, filtering, fetch and errors.

Fully offline: the only transport is a stub session that raises on any request
it has not been primed with, so a real network call is impossible in these
tests (and would fail loudly).
"""

from __future__ import annotations

from io import BytesIO

import pytest
import requests
from PIL import Image

from deckforge_core.config import SecretStore
from deckforge_core.errors import ImageError
from deckforge_core.images.providers import PexelsProvider, UnsplashProvider
from deckforge_core.providers.images import ImageItem


class FakeResponse:
    def __init__(self, payload=None, content=b"", status_code=200):
        self._payload = payload if payload is not None else {}
        self.content = content
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)


class StubSession:
    """The only transport in sight. Unprimed requests fail loudly instead of
    touching the network."""

    def __init__(self, responses=(),
                 failing: bool = False):
        self._responses = list(responses)
        self._failing = failing
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self._failing:
            raise requests.ConnectionError("no network available")
        if not self._responses:
            raise AssertionError(f"unexpected network request to {url}")
        return self._responses.pop(0)


def png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(buf, "PNG")
    return buf.getvalue()


def unsplash_result(pid, w, h, name="Jane Doe", color="#abcdef"):
    return {
        "id": pid,
        "width": w,
        "height": h,
        "urls": {
            "thumb": f"https://x/{pid}/thumb",
            "small": f"https://x/{pid}/small",
            "regular": f"https://x/{pid}/img",
            "raw": f"https://x/{pid}/raw",
            "full": f"https://x/{pid}/full",
        },
        "color": color,
        "user": {"name": name},
        "links": {"html": f"https://unsplash.com/photos/{pid}"},
        "alt_description": f"alt {pid}",
        "description": "",
    }


def pexels_result(pid, w, h, photographer="John Roe", alt="alt p", color="#123456"):
    return {
        "id": pid,
        "width": w,
        "height": h,
        "url": f"https://www.pexels.com/photo/{pid}",
        "photographer": photographer,
        "alt": alt,
        "avg_color": color,
        "src": {
            "original": f"https://p/{pid}/orig",
            "large2x": f"https://p/{pid}/l2x",
            "large": f"https://p/{pid}/l",
            "medium": f"https://p/{pid}/med",
            "small": f"https://p/{pid}/small",
        },
    }


@pytest.fixture
def no_secret(monkeypatch):
    monkeypatch.setattr(SecretStore, "get", lambda self, provider, default=None: None)


def test_unsplash_search_maps_and_filters(no_secret):
    responses = [
        FakeResponse(
            {"results": [
                unsplash_result("good", 4000, 3000, name="Jane Doe"),
                unsplash_result("small", 300, 200, name="Tiny"),
                unsplash_result("tall-narrow", 1600, 400, name="Banner"),
            ]}
        )
    ]
    stub = StubSession(responses)
    provider = UnsplashProvider(api_key="test-key", session=stub)

    items = provider.search("city", limit=4, min_width=800, min_height=600)

    assert len(items) == 1
    got = items[0]
    assert got.id == "good"
    assert got.provider == "unsplash"
    assert got.thumb_url == "https://x/good/thumb"
    assert got.width == 4000 and got.height == 3000
    assert got.license == "Unsplash license"
    assert got.attribution == "Photo by Jane Doe on Unsplash"
    assert got.page_url == "https://unsplash.com/photos/good"
    assert got.alt == "alt good"
    assert got.color == "#abcdef"


def test_unsplash_search_sends_params_and_auth(no_secret):
    stub = StubSession([FakeResponse({"results": []})])
    provider = UnsplashProvider(api_key="test-key", session=stub)

    provider.search("mountains", limit=8, min_width=800, min_height=600, orientation="portrait")

    url, kwargs = stub.calls[0]
    assert url == "https://api.unsplash.com/search/photos"
    assert kwargs["params"]["query"] == "mountains"
    assert kwargs["params"]["per_page"] == 8
    assert kwargs["params"]["orientation"] == "portrait"
    assert kwargs["headers"]["Authorization"] == "Client-ID test-key"


def test_unsplash_fetch_writes_canned_bytes(no_secret, tmp_path):
    data = png_bytes()
    stub = StubSession([FakeResponse(content=data)])
    provider = UnsplashProvider(api_key="test-key", session=stub)
    item = ImageItem(
        id="p1", provider="unsplash", url="https://x/p1.jpg", width=4000, height=3000
    )

    dest = provider.fetch(item, tmp_path / "out" / "p1.jpg")

    assert dest.exists()
    assert dest.read_bytes() == data
    assert dest.parent.is_dir()


def test_unsplash_missing_key_only_fails_on_call(no_secret):
    stub = StubSession([])
    provider = UnsplashProvider(api_key=None, session=stub)
    assert provider.healthcheck() == "unsplash (no key)"

    with pytest.raises(ImageError):
        provider.search("city")

    assert stub.calls == []


def test_unsplash_network_error_wrapped(no_secret):
    stub = StubSession(failing=True)
    provider = UnsplashProvider(api_key="test-key", session=stub)

    with pytest.raises(ImageError, match="request failed"):
        provider.search("city")


def test_unsplash_healthcheck_offline(no_secret):
    stub = StubSession([])
    provider = UnsplashProvider(api_key="abc", session=stub)
    assert provider.healthcheck() == "unsplash (key configured)"
    assert stub.calls == []


def test_pexels_search_maps(no_secret):
    stub = StubSession(
        [FakeResponse({"photos": [pexels_result("ph1", 5000, 3300, photographer="John Roe")]})]
    )
    provider = PexelsProvider(api_key="test-key", session=stub)

    items = provider.search("sunset", limit=8, min_width=800, min_height=600)

    assert len(items) == 1
    got = items[0]
    assert got.provider == "pexels"
    assert got.url == "https://p/ph1/orig"
    assert got.thumb_url == "https://p/ph1/med"
    assert got.width == 5000 and got.height == 3300
    assert got.license == "Pexels license"
    assert got.attribution == "Photo by John Roe on Pexels"
    assert got.page_url == "https://www.pexels.com/photo/ph1"
    assert got.alt == "alt p"
    assert got.color == "#123456"

    url, kwargs = stub.calls[0]
    assert url == "https://api.pexels.com/v1/search"
    assert kwargs["params"]["query"] == "sunset"
    assert kwargs["headers"]["Authorization"] == "test-key"


def test_pexels_http_error_wrapped(no_secret):
    stub = StubSession([FakeResponse(payload={}, status_code=500)])
    provider = PexelsProvider(api_key="test-key", session=stub)

    with pytest.raises(ImageError):
        provider.search("sunset")


def test_pexels_healthcheck_offline(no_secret):
    stub = StubSession([])
    provider = PexelsProvider(api_key=None, session=stub)
    assert provider.healthcheck() == "pexels (no key)"
    assert stub.calls == []


def test_provider_fetch_writes_bytes_for_pexels(no_secret, tmp_path):
    data = png_bytes()
    stub = StubSession([FakeResponse(content=data)])
    provider = PexelsProvider(api_key="test-key", session=stub)
    item = ImageItem(
        id="ph1", provider="pexels", url="https://p/ph1/orig", width=5000, height=3300
    )

    dest = provider.fetch(item, tmp_path / "p1.jpg")

    assert dest.read_bytes() == data

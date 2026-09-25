"""Local photo library tests: indexing, deterministic search, fetch cache.

Fully offline — images are generated with PIL in a temp dir.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from deckforge_core.config import SecretStore
from deckforge_core.images import LocalPhotoLibrary, dhash, fetch_and_store, search_images


def make_png(path: Path, size: tuple[int, int], rgb: tuple[int, int, int]) -> None:
    Image.new("RGB", size, rgb).save(path, "PNG")


@pytest.fixture
def photo_root(tmp_path) -> Path:
    root = tmp_path / "photos"
    root.mkdir()
    make_png(root / "a_red.png", (200, 300), (200, 40, 40))
    make_png(root / "b_blue.png", (800, 600), (40, 80, 220))
    make_png(root / "c_neutral.png", (400, 400), (140, 140, 140))
    return root


@pytest.fixture
def library(photo_root) -> LocalPhotoLibrary:
    return LocalPhotoLibrary(photo_root)


def test_index_count(library):
    assert library.index_count() == 3


def test_all_items_are_deterministic_local_items(library, photo_root):
    items = library.all_items()
    urls = [i.url for i in items]
    assert len(items) == 3
    assert urls == sorted(urls, key=str)
    assert [i.id for i in items] == [i.id for i in library.all_items()]

    blue = [i for i in items if i.width == 800][0]
    assert blue.provider == "local"
    assert blue.url.startswith("file://")
    assert blue.id.startswith(str(photo_root))
    assert blue.license == "local"
    assert blue.attribution == "Local library photo"
    assert len(blue.color) == 7 and blue.color.startswith("#")


def test_all_items_sizes(library):
    by_name = {i.alt: i for i in library.all_items()}
    assert by_name["b_blue.png"].width == 800 and by_name["b_blue.png"].height == 600
    assert by_name["a_red.png"].width == 200 and by_name["a_red.png"].height == 300
    assert by_name["c_neutral.png"].width == 400 and by_name["c_neutral.png"].height == 400


def test_search_by_color_prefers_blue(library):
    items = library.search("blue", limit=3)
    assert items[0].width == 800
    assert items[0].height == 600


def test_search_by_orientation_landscape(library):
    items = library.search("landscape")
    assert items[0].width == 800


def test_search_by_orientation_portrait(library):
    items = library.search("portrait")
    assert items[0].width == 200


def test_search_by_orientation_square(library):
    items = library.search("square")
    assert items[0].width == 400
    assert items[0].height == 400


def test_search_is_deterministic(library):
    assert [i.id for i in library.search("blue")] == [i.id for i in library.search("BLUE")]
    assert [i.id for i in library.search("warm")] == [i.id for i in library.search("warm")]


def test_dhash_is_deterministic(photo_root):
    path = photo_root / "b_blue.png"
    h1 = dhash(path)
    h2 = dhash(path)
    assert h1 == h2
    assert len(h1) == 16
    assert int(h1, 16) >= 0


def test_empty_and_missing_root_do_not_crash(tmp_path):
    missing = LocalPhotoLibrary(tmp_path / "does-not-exist")
    assert missing.index_count() == 0
    assert missing.all_items() == []
    assert missing.search("blue") == []

    empty = LocalPhotoLibrary(tmp_path / "empty_photos")
    empty.root.mkdir()
    assert empty.index_count() == 0


def test_fetch_and_store_local_dedupes(photo_root, tmp_path):
    lib = LocalPhotoLibrary(photo_root)
    item = [i for i in lib.all_items() if i.width == 800][0]
    cache = tmp_path / "cache"

    first = fetch_and_store(item, cache)
    second = fetch_and_store(item, cache)

    assert first == second
    assert first.exists()
    assert first.suffix == ".png"
    assert "local" in first.parts
    files = [p for p in first.parent.iterdir()]
    assert len(files) == 1


def test_search_images_local_source(photo_root, monkeypatch):
    monkeypatch.setattr(SecretStore, "get", lambda self, provider, default=None: None)
    items = search_images(["unsplash", "pexels", "local"], "blue", local_root=photo_root)
    assert len(items) == 1
    assert items[0].provider == "local"
    assert items[0].width == 800

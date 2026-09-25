"""Deterministic local photo library index (no external model dependencies).

For every supported image under the root we store its size, an average colour,
a dominant *cluster* colour (histogram of 8x8-block means bucketed to /32), and
a 64-bit dhash. ``search`` is a light, fully local scorer driven by colour /
orientation words in the query; ties always resolve deterministically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageStat

from deckforge_core.logging_util import get_logger
from deckforge_core.providers.images import ImageItem

log = get_logger("deckforge.images.local")

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

_IMAGE_TOKEN = re.compile(r"[a-z0-9]+")

_COLOR_WORDS: dict[str, tuple[int, int, int]] = {
    "red": (200, 40, 40),
    "blue": (40, 80, 220),
    "green": (50, 180, 90),
    "yellow": (225, 190, 40),
    "orange": (235, 130, 40),
    "purple": (130, 60, 200),
    "pink": (235, 120, 160),
    "brown": (130, 85, 45),
    "grey": (130, 130, 130),
    "gray": (130, 130, 130),
    "white": (245, 245, 245),
    "black": (30, 30, 30),
    "teal": (40, 160, 170),
    "indigo": (70, 60, 190),
    "warm": (225, 150, 80),
    "cool": (80, 130, 200),
}

_ORIENTATION_WORDS: dict[str, float] = {
    "landscape": 16 / 9,
    "wide": 2.0,
    "horizontal": 16 / 9,
    "portrait": 9 / 16,
    "tall": 0.5,
    "vertical": 9 / 16,
    "square": 1.0,
    "squarish": 1.0,
}


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in rgb)


def _avg_color(im: Image.Image) -> tuple[int, int, int]:
    thumb = im.convert("RGB").resize((32, 32), Image.Resampling.BILINEAR)
    stat = ImageStat.Stat(thumb)
    return tuple(int(round(v)) for v in stat.mean)  # type: ignore[return-value]


def _dominant_cluster(im: Image.Image) -> tuple[int, int, int]:
    width, height = im.size
    scale = min(1.0, 512 / max(width, height))
    small = im.convert("RGB").resize(
        (max(8, int(width * scale)), max(8, int(height * scale))),
        Image.Resampling.BILINEAR,
    )
    sw, sh = small.size
    buckets: dict[tuple[int, int, int], int] = {}
    for by in range(sh // 8):
        for bx in range(sw // 8):
            box = (bx * 8, by * 8, bx * 8 + 8, by * 8 + 8)
            stat = ImageStat.Stat(small.crop(box))
            r, g, b = (int(v) for v in stat.mean)
            bucket = ((r // 32) * 32, (g // 32) * 32, (b // 32) * 32)
            buckets[bucket] = buckets.get(bucket, 0) + 1
    if not buckets:
        return _avg_color(im)
    dominant, _ = max(buckets.items(), key=lambda kv: (kv[1], -kv[0][0], -kv[0][1]))
    return dominant


def dhash(source: Path | str | Image.Image) -> str:
    """64-bit dhash (9x8 adjacent-pixel gradient) as 16 hex chars.

    Deterministic for identical pixel data.
    """
    if isinstance(source, (str, Path)):
        with Image.open(source) as im:
            im.load()
            return _dhash(im)
    return _dhash(source)


def _dhash(im: Image.Image) -> str:
    grey = im.convert("L").resize((9, 8), Image.Resampling.BILINEAR)
    width, height = grey.size
    px = list(grey.tobytes())
    bits = 0
    for row in range(height):
        base = row * width
        for col in range(width - 1):
            bits = (bits << 1) | (1 if px[base + col] > px[base + col + 1] else 0)
    return f"{bits:016x}"


@dataclass
class _PhotoEntry:
    path: Path
    width: int
    height: int
    avg_rgb: tuple[int, int, int]
    dominant_rgb: tuple[int, int, int]
    hash: str

    @property
    def area(self) -> int:
        return self.width * self.height


class LocalPhotoLibrary:
    """Indexes every image under ``root`` once, then serves deterministic
    ``search``/``all_items`` results. An empty or nonexistent root yields an
    empty library rather than raising."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)
        self._entries: list[_PhotoEntry] = []
        self._build_index()

    def _build_index(self) -> None:
        if not self._root.is_dir():
            return
        for path in sorted(
            (
                p
                for p in self._root.rglob("*")
                if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
            ),
            key=str,
        ):
            try:
                with Image.open(path) as im:
                    im.load()
                    width, height = im.size
                    avg = _avg_color(im)
                    dominant = _dominant_cluster(im)
            except Exception:
                log.warning("local library: skipped unreadable image %s", path)
                continue
            self._entries.append(
                _PhotoEntry(
                    path=path,
                    width=int(width),
                    height=int(height),
                    avg_rgb=avg,
                    dominant_rgb=dominant,
                    hash=dhash(path),
                )
            )

    @property
    def root(self) -> Path:
        return self._root

    def index_count(self) -> int:
        return len(self._entries)

    def _to_item(self, entry: _PhotoEntry) -> ImageItem:
        rel = entry.path.relative_to(self._root).as_posix()
        return ImageItem(
            id=f"{self._root}-{rel}",
            provider="local",
            url=entry.path.as_uri(),
            thumb_url="",
            width=entry.width,
            height=entry.height,
            license="local",
            attribution="Local library photo",
            page_url="",
            alt=entry.path.name,
            color=_hex(entry.avg_rgb),
        )

    def all_items(self, limit: int | None = None) -> list[ImageItem]:
        items = [self._to_item(e) for e in self._entries]
        if limit is not None:
            items = items[: limit]
        return items

    def search(self, query: str, limit: int = 8) -> list[ImageItem]:
        tokens = set(_IMAGE_TOKEN.findall((query or "").lower()))
        target_rgb: tuple[int, int, int] | None = None
        dark = "dark" in tokens
        light = "light" in tokens
        for word, rgb in _COLOR_WORDS.items():
            if word in tokens:
                target_rgb = rgb
                break
        if target_rgb is None:
            if dark:
                target_rgb = (25, 25, 25)
            elif light:
                target_rgb = (245, 245, 245)
        elif dark:
            target_rgb = tuple(int(v * 0.5) for v in target_rgb)
        elif light:
            target_rgb = tuple(int(v * 0.5 + 0.5 * 245) for v in target_rgb)

        target_ratio: float | None = None
        for word, ratio in _ORIENTATION_WORDS.items():
            if word in tokens:
                target_ratio = ratio
                break

        def score(entry: _PhotoEntry) -> tuple:
            colour = 0.0
            if target_rgb is not None:
                colour = _rgb_distance(entry.dominant_rgb, target_rgb)
            orientation = 0.0
            if target_ratio is not None:
                ratio = entry.width / max(entry.height, 1)
                orientation = abs(ratio - target_ratio) / max(target_ratio, 1e-9)
            return (colour, orientation, -entry.area, entry.path.as_posix())

        ranked = sorted(self._entries, key=score)
        return [self._to_item(e) for e in ranked[:limit]]


def _rgb_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    from math import sqrt

    return sqrt(sum((x - y) ** 2 for x, y in zip(a, b))) / (255.0 * sqrt(3))


def walk(root: Path | str) -> Iterable[Path]:
    """Public helper: iterate the supported image files under ``root`` in order."""
    for path in sorted(
        (
            p
            for p in Path(root).rglob("*")
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
        ),
        key=str,
    ):
        yield path

"""Result quality filters and deterministic ranking for photos.

Model-free heuristics: minimum resolution, aspect-fit against a target ratio,
a conservative watermark sniff, and a lexicographic score (aspect match over
resolution over colour nearness) so ordering is stable across runs.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageStat

from deckforge_core.providers.images import ImageItem

_ASPECT_TOLERANCE = 0.15


def is_large_enough(item: ImageItem, min_w: int, min_h: int) -> bool:
    """True when the item is at least ``min_w`` by ``min_h`` pixels."""
    return item.width >= min_w and item.height >= min_h


def image_ratio(item: ImageItem) -> float:
    return item.width / max(item.height, 1)


def has_acceptable_aspect(
    item: ImageItem, target_ratio: float, tolerance: float = _ASPECT_TOLERANCE
) -> bool:
    """True when the item aspect (w/h) is within ``tolerance`` of the target."""
    target = float(target_ratio)
    if target <= 0:
        return True
    ratio = image_ratio(item)
    return abs(ratio - target) / target <= tolerance


def looks_watermarked(path: Path) -> bool:
    """Conservative heuristic for repeated bright low-variance patches.

    Pure PIL: the image is flattened to grey and split into a coarse grid; a
    suspicious photo has several flat+bright cells while the image as a whole
    is not uniformly near-white. Deliberately strict so it rarely flags real
    photos (bright skies, white backdrops) as watermarked.
    """
    try:
        with Image.open(path) as im:
            grey = im.convert("L").resize((96, 72), Image.Resampling.BILINEAR)
    except Exception:
        return False
    overall = ImageStat.Stat(grey).mean[0]
    if overall >= 235:
        return False
    cols, rows, pw, ph = 8, 6, 12, 12
    flat_bright = 0
    total = 0
    for row in range(rows):
        for col in range(cols):
            box = (col * pw, row * ph, (col + 1) * pw, (row + 1) * ph)
            stat = ImageStat.Stat(grey.crop(box))
            total += 1
            if stat.mean[0] >= 210 and stat.stddev[0] <= 5:
                flat_bright += 1
    return flat_bright >= 6 and flat_bright >= 0.2 * total


class QualityFilter:
    """Grouped view of the module-level quality predicates."""

    is_large_enough = staticmethod(is_large_enough)
    has_acceptable_aspect = staticmethod(has_acceptable_aspect)
    looks_watermarked = staticmethod(looks_watermarked)


def _parse_hex(color: str) -> tuple[int, int, int]:
    value = color.strip().lstrip("#")
    if len(value) != 6:
        return (128, 128, 128)
    try:
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return (128, 128, 128)


def _average_local_color(item: ImageItem) -> tuple[int, int, int] | None:
    if not item.url.startswith("file://"):
        return None
    from urllib.parse import unquote, urlparse
    from urllib.request import url2pathname

    try:
        path = Path(url2pathname(unquote(urlparse(item.url).path)))
        with Image.open(path) as im:
            thumb = im.convert("RGB").resize((32, 32), Image.Resampling.BILINEAR)
        stat = ImageStat.Stat(thumb)
        return tuple(int(round(v)) for v in stat.mean)
    except Exception:
        return None


def _color_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return math.dist(a, b) / (255.0 * math.sqrt(3))


def _color_closeness(item: ImageItem, query_color: str) -> float:
    target = _parse_hex(query_color)
    rgb: tuple[int, int, int] | None = None
    if len(item.color.strip().lstrip("#")) == 6:
        rgb = _parse_hex(item.color)
    else:
        rgb = _average_local_color(item)
    if rgb is None:
        return 0.5  # neutral: unknown colour neither helps nor hurts
    return 1.0 - _color_distance(rgb, target)


def rank_results(
    items: list[ImageItem],
    target_ratio: float,
    query_color: str | None = None,
    prefer_wider: bool = True,
) -> list[ImageItem]:
    """Return ``items`` ordered by fit: aspect match, then resolution, then
    colour nearness. Deterministic: ties break by item id."""
    target = float(target_ratio)

    def key(item: ImageItem) -> tuple:
        ratio = image_ratio(item)
        penalty = abs(ratio - target) / max(target, 1e-9)
        acceptable = 0 if penalty <= _ASPECT_TOLERANCE else 1
        if prefer_wider:
            resolution = (-item.width, -item.height)
        else:
            resolution = (-(item.width * item.height), -item.width)
        colour = 0.0
        if query_color:
            colour = -_color_closeness(item, query_color)
        # penalty is quantized so only genuinely different aspect fits break
        # ties; equal fits fall through to resolution (width-vs-area ordering).
        return (acceptable, round(penalty, 4), *resolution, colour, item.id)

    return sorted(items, key=key)


def pick_best(items: list[ImageItem], target_dims: tuple[int, int]) -> ImageItem | None:
    """Single best choice for ``target_dims`` (width, height) via ``rank_results``."""
    if not items:
        return None
    target_ratio = target_dims[0] / max(target_dims[1], 1)
    ranked = rank_results(items, target_ratio)
    return ranked[0] if ranked else None

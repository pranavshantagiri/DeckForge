"""Slide canvas geometry: aspect-ratio -> EMU size plus unit conversions.

Blueprints are authored in RELATIVE units (fractions of slide width/height,
0..1). This module knows how to translate between physical units (EMU, inch,
px) and those relative fractions — nothing about layout or margins, which live
in :mod:`deckforge_core.renderer.layout`.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from typing import Optional, Tuple

EMU_PER_INCH = 914400
EMU_PER_PX = 9525  # 96 dpi
EMU_PER_PT = 12700  # 1/72 inch

_DEFAULT_ASPECT = "16:9"

_CUSTOM_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)?)(px|emu)?\s*[x×]\s*(\d+(?:\.\d+)?)(px|emu)?\s*$"
)

#: Named aspect ratios -> (width_emu, height_emu).
_NAMED_SIZES: dict[str, Tuple[int, int]] = {
    "16:9": (12192000, 6858000),
    "16:10": (12192000, 7620000),
    "4:3": (9144000, 6858000),
    "a4": (7560000, 10692000),
    "portrait": (7560000, 10692000),
    "letter-portrait": (7772400, 10058400),
}


@dataclass(frozen=True)
class Canvas:
    """A slide canvas in EMUs."""

    width_emu: int
    height_emu: int

    @property
    def aspect_ratio(self) -> float:
        return self.width_emu / self.height_emu

    @classmethod
    def from_ratio(cls, aspect_ratio: str) -> "Canvas":
        w, h = canvas_size(aspect_ratio)
        return cls(w, h)


def canvas_size(aspect_ratio: str) -> Tuple[int, int]:
    """Return ``(width_emu, height_emu)`` for an aspect-ratio string.

    Known named ratios have fixed EMU sizes. Custom sizes are parsed as
    ``WxH`` where bare numbers are EMUs and a ``px`` suffix multiplies by the
    96-dpi EMU-per-px factor. Any numeric ratio with width < height resolves to
    the portrait canvas so portrait plans never get squashed onto a landscape
    slide. Unknown ratios (and equal ratios) fall back to 16:9 with a
    ``RuntimeWarning``.
    """
    key = (aspect_ratio or "").strip().lower()
    if key in _NAMED_SIZES:
        return _NAMED_SIZES[key]
    parsed = _parse_custom(key)
    if parsed is not None:
        w, h = parsed
        if w > 0 and h > 0:
            return w, h
    ratio = _parse_ratio(key)
    if ratio is not None:
        if ratio < 1.0:  # numeric portrait ratio -> portrait canvas, never squash
            return _NAMED_SIZES["portrait"]
        warnings.warn(
            f"unknown aspect ratio {aspect_ratio!r}; defaulting to {_DEFAULT_ASPECT}",
            category=RuntimeWarning,
            stacklevel=2,
        )
        return _NAMED_SIZES[_DEFAULT_ASPECT]
    warnings.warn(
        f"unknown aspect ratio {aspect_ratio!r}; defaulting to {_DEFAULT_ASPECT}",
        category=RuntimeWarning,
        stacklevel=2,
    )
    return _NAMED_SIZES[_DEFAULT_ASPECT]


def _parse_custom(key: str) -> Optional[Tuple[int, int]]:
    """Parse ``WxH`` with an optional trailing ``px``/``emu`` unit.

    ``1920x1080px`` means both dimensions are pixels; ``914400x685800`` (no
    unit) means both are EMUs. Mixed units are not supported.
    """
    match = _CUSTOM_RE.match(key)
    if match is None:
        return None
    width_token, width_unit, height_token, height_unit = match.groups()
    unit = (width_unit or height_unit or "emu").lower()
    factor = float(EMU_PER_PX) if unit == "px" else 1.0
    width = float(width_token) * factor
    height = float(height_token) * factor
    if width <= 0 or height <= 0:
        return None
    return int(round(width)), int(round(height))


def _parse_ratio(key: str) -> Optional[float]:
    try:
        number, denom = key.split(":")
        ratio = float(number) / float(denom)
    except (ValueError, ZeroDivisionError):
        return None
    return ratio if ratio > 0 else None


# --------------------------------------------------------------------------- #
# Conversion helpers
# --------------------------------------------------------------------------- #
def emu_to_inch(emu: int) -> float:
    return emu / EMU_PER_INCH


def inch_to_emu(inch: float) -> int:
    return int(round(inch * EMU_PER_INCH))


def emu_to_relative(emu: int, total_emu: int) -> float:
    if total_emu <= 0:
        raise ValueError("total_emu must be positive")
    return emu / total_emu


def relative_to_emu(frac: float, total_emu: int) -> int:
    return int(round(frac * total_emu))


def font_pt_to_emu(pt: float) -> int:
    return int(round(pt * EMU_PER_PT))

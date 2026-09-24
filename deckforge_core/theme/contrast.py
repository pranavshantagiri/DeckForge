"""WCAG 2.x relative luminance and contrast helpers for theme generation.

Pure math (no numpy) so the module is dependency-free and trivially testable.
"""

from __future__ import annotations


def _rgb(hex_color: str) -> tuple[float, float, float]:
    """Return sRGB channels of ``#RRGGBB`` as floats in 0..1."""
    h = hex_color.lstrip("#")
    return int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0


def _linearize(channel: float) -> float:
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    """WCAG 2.x relative luminance of ``#RRGGBB`` (0.0 black .. 1.0 white)."""
    r, g, b = _rgb(hex_color)
    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    """WCAG contrast ratio between two hex colours, always >= 1.0."""
    la = relative_luminance(hex_a)
    lb = relative_luminance(hex_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def is_pass(hex_a: str, hex_b: str, *, large: bool = False) -> bool:
    """True if contrast passes WCAG (>=4.5 normal, >=3.0 large text/graphics)."""
    threshold = 3.0 if large else 4.5
    return contrast_ratio(hex_a, hex_b) >= threshold


_LIGHT_TEXT = "#FFFFFF"
_DARK_TEXT = "#1C1C1A"


def accessible_text_colors(on_bg_hex: str) -> list[str]:
    """White + near-black candidates passing >=4.5:1 on ``on_bg_hex``, by ratio.

    Sorted strongest contrast first.
    """
    candidates = [_LIGHT_TEXT, _DARK_TEXT]
    passing = [c for c in candidates if is_pass(c, on_bg_hex)]
    return sorted(passing, key=lambda c: contrast_ratio(c, on_bg_hex), reverse=True)

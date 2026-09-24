"""StyleProfile construction from a natural-language brief.

Palette roles are derived from mood keywords with HSL math, then contrast
guarantees (WCAG text/bg >= 4.5, accent1/bg >= 3, muted-text/bg >= 3) are
enforced iteratively. Fonts come from :mod:`fonts`, type scale from sensible
defaults. Everything is deterministic for a given (brief, seed).
"""

from __future__ import annotations

import colorsys

from deckforge_core.schemas.pack import (
    ColorPalette,
    FontPair,
    Grid,
    ImageTreatment,
    Margins,
    PaletteColor,
    StyleConfidence,
    StyleProfile,
    TypeScale,
    TypeScaleEntry,
)
from deckforge_core.theme.contrast import contrast_ratio
from deckforge_core.theme.fonts import look_contrast, pair_for_brief


# --------------------------------------------------------------------------- #
# HSL helpers
# --------------------------------------------------------------------------- #
def hls_to_hex(h: float, lightness: float, s: float) -> str:
    """Convert HLS (h in degrees 0..360, l/s in 0..1) to an upper-case hex."""
    r, g, b = colorsys.hls_to_rgb(h / 360.0, lightness, s)
    return "#{:02X}{:02X}{:02X}".format(
        int(round(r * 255)), int(round(g * 255)), int(round(b * 255))
    )


def hex_to_hls(hex_color: str) -> tuple[float, float, float]:
    """Convert ``#RRGGBB`` to (h degrees, lightness, saturation)."""
    hx = hex_color.lstrip("#")
    r, g, b = int(hx[0:2], 16) / 255.0, int(hx[2:4], 16) / 255.0, int(hx[4:6], 16) / 255.0
    h, lightness, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360.0, lightness, s


def darken_hex(hex_color: str, amount: float = 0.02) -> str:
    """Reduce lightness by ``amount``, clamped to a non-negative floor."""
    h, lightness, s = hex_to_hls(hex_color)
    return hls_to_hex(h, max(lightness - amount, 0.04), s)


def shade_hex(hex_color: str, fraction: float) -> str:
    """Scale lightness by ``fraction`` (0..1) keeping hue/saturation."""
    h, lightness, s = hex_to_hls(hex_color)
    return hls_to_hex(h, max(min(lightness * fraction, 1.0), 0.04), s)


# --------------------------------------------------------------------------- #
# Brief -> mood -> hue/saturation
# --------------------------------------------------------------------------- #
# Fixed rule scan order keeps combination deterministic regardless of how the
# keywords appear in the text.
_MOOD_RULES: dict[str, tuple[str, str, str]] = {
    "calm": ("hue", "210"),
    "serene": ("hue", "210"),
    "editorial": ("hue", "35"),
    "classic": ("saturate", "0.10"),
    "modern": ("hue", "25"),
    "clean": ("saturate", "0.10"),
    "minimal": ("saturate", "0.12"),
    "energetic": ("saturate", "0.55"),
    "bold": ("saturate", "0.55"),
    "vibrant": ("saturate", "0.65"),
    "corporate": ("hue", "220"),
    "professional": ("saturate", "0.25"),
    "playful": ("hue", "300"),
    "fun": ("saturate", "0.50"),
    "warm": ("warm", ""),
    "neutral": ("saturate", "0.12"),
}

_DEFAULT_HUE = 40.0
_DEFAULT_SAT = 0.15


def _mood_hue_sat(brief: str, seed: int) -> tuple[float, float, list[str]]:
    """Return (hue, saturation) and matched mood keywords for a brief."""
    lower = brief.lower()
    hue = _DEFAULT_HUE
    sat = _DEFAULT_SAT
    matched: list[str] = []
    for kw, (op, value) in _MOOD_RULES.items():
        if kw in lower:
            matched.append(kw)
            if op == "hue":
                hue = float(value)
            elif op == "saturate":
                sat = float(value)
            elif op == "warm":
                hue = (hue + 20.0) % 360.0
                sat = min(sat + 0.05, 0.6)
    hue = (hue + ((seed % 7) - 3)) % 360.0
    return hue, min(max(sat, 0.08), 0.7), matched


def _build_palette_colors(hue: float, sat: float) -> list[PaletteColor]:
    """Construct role colors from a base hue + saturation, with usage weights."""
    accent_sat = min(0.75, max(sat * 1.2, 0.4))
    bg = hls_to_hex(hue, 0.97, max(sat * 0.5, 0.02))
    text = hls_to_hex(hue, 0.13, min(sat * 0.15, 0.1))
    muted = hls_to_hex(hue, 0.45, min(sat * 0.4, 0.15))
    accent1 = hls_to_hex(hue, 0.42, accent_sat)
    accent2 = hls_to_hex((hue + 145.0) % 360.0, 0.46, accent_sat)
    neutral1 = hls_to_hex(hue, 0.84, 0.04)
    line = hls_to_hex(hue, 0.72, 0.05)
    return [
        PaletteColor(role="bg", hex=bg, usage_pct=40.0),
        PaletteColor(role="text", hex=text, usage_pct=22.0),
        PaletteColor(role="muted-text", hex=muted, usage_pct=14.0),
        PaletteColor(role="accent1", hex=accent1, usage_pct=12.0),
        PaletteColor(role="accent2", hex=accent2, usage_pct=6.0),
        PaletteColor(role="neutral1", hex=neutral1, usage_pct=4.0),
        PaletteColor(role="line", hex=line, usage_pct=2.0),
    ]


_CONSTRAINTS = (
    ("text", "bg", 4.5),
    ("muted-text", "bg", 3.0),
    ("accent1", "bg", 3.0),
)

_CONSERVATIVE_TEXT = "#141412"
_CONSERVATIVE_BG = "#FFFFFF"


def _enforce_contrast(colors: list[PaletteColor]) -> list[str]:
    """Darken foreground roles until WCAG minima are met; return failure notes."""
    notes: list[str] = []
    by_role = {c.role: c for c in colors}
    for fg_role, bg_role, minimum in _CONSTRAINTS:
        fg = by_role[fg_role]
        current = fg.hex
        for _ in range(10):
            if contrast_ratio(current, by_role[bg_role].hex) >= minimum:
                break
            current = darken_hex(current, 0.02)
        else:
            notes.append(
                f"contrast guarantee {fg_role}/{bg_role} >= {minimum} not met in 10 "
                "steps; clamped to conservative tone"
            )
            current = _CONSERVATIVE_TEXT
            if by_role[bg_role].role == "bg":
                by_role["bg"].hex = _CONSERVATIVE_BG
        fg.hex = current
    return notes


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def palette_from_brief(brief: str, seed: int = 0) -> ColorPalette:
    """Deterministic ColorPalette derived from ``brief`` mood keywords."""
    hue, sat, _ = _mood_hue_sat(brief, seed)
    colors = _build_palette_colors(hue, sat)
    _enforce_contrast(colors)
    return ColorPalette(colors=colors)


def _type_scale() -> TypeScale:
    return TypeScale(
        entries=[
            TypeScaleEntry(name="kicker", size_pt=12, weight="medium", caps="upper"),
            TypeScaleEntry(name="h1", size_pt=40, weight="bold"),
            TypeScaleEntry(name="h2", size_pt=28, weight="bold"),
            TypeScaleEntry(name="body", size_pt=16, weight="regular", line_spacing=1.2),
            TypeScaleEntry(name="small", size_pt=12, weight="regular"),
            TypeScaleEntry(name="big-number", size_pt=80, weight="bold"),
            TypeScaleEntry(name="caption", size_pt=10, weight="regular"),
        ]
    )


def style_from_brief(brief: str, *, aspect_ratio: str = "16:9", seed: int = 0) -> StyleProfile:
    """Build a validated :class:`StyleProfile` from a brief, deterministically."""
    hue, sat, matched = _mood_hue_sat(brief, seed)
    colors = _build_palette_colors(hue, sat)
    wore_notes = _enforce_contrast(colors)
    palette = ColorPalette(colors=colors)
    fonts: FontPair = pair_for_brief(brief, seed)

    actual = contrast_ratio(colors[0].hex, colors[1].hex)  # bg vs text
    notes = [
        f"palette base from mood keywords {matched or ['neutral-warm (default)']} "
        f"(hue {hue:0.0f}deg, sat {sat:0.2f})",
        f"fonts {fonts.heading}/{fonts.body} ({look_contrast(fonts)} heading-vs-body contrast)",
        f"guaranteed text/bg contrast >= 4.5 (actual {actual:.2f})",
        f"default type scale; aspect ratio {aspect_ratio}; seed {seed}",
        *wore_notes,
    ]

    profile = StyleProfile.model_validate(
        {
            "version": 1,
            "palette": palette,
            "fonts": fonts,
            "type_scale": _type_scale(),
            "margins": Margins(),
            "grid": Grid(columns=12),
            "corner_radii": 0.02,
            "line_weight_pt": 1.0,
            "image_treatment": ImageTreatment(mode="framed", corner_radius=0.02),
            "density": {},
            "confidence": StyleConfidence(overall=0.7, palette=0.75, fonts=0.7, grid=0.9, layout=0.6),
            "notes": notes,
        }
    )
    return profile

"""Safe font stacks and deterministic brief -> FontPair routing.

Only commonly-installed, license-clean families that ship with Windows are
listed, so no font bundling is required on the target runtime.
"""

from __future__ import annotations

import random

from deckforge_core.schemas.pack import FontPair

SAFE_FONTS: list[dict[str, str]] = [
    {"name": "Arial", "kind": "sans"},
    {"name": "Helvetica", "kind": "sans"},
    {"name": "Calibri", "kind": "sans"},
    {"name": "Segoe UI", "kind": "humanist"},
    {"name": "Georgia", "kind": "serif"},
    {"name": "Cambria", "kind": "serif"},
    {"name": "Tahoma", "kind": "humanist"},
    {"name": "Verdana", "kind": "humanist"},
    {"name": "Trebuchet MS", "kind": "humanist"},
]

FONT_NAMES: list[str] = [f["name"] for f in SAFE_FONTS]


def font_kind(name: str) -> str:
    """Return 'sans' / 'serif' / 'humanist' for a family, defaulting to 'sans'."""
    for f in SAFE_FONTS:
        if f["name"] == name:
            return f["kind"]
    return "sans"


# (keywords, heading, body) in descending priority; scored by keyword hits.
_FONT_RULES: list[tuple[tuple[str, ...], str, str]] = [
    (("editorial", "classic", "serif"), "Georgia", "Arial"),
    (("modern", "clean", "minimal"), "Segoe UI", "Calibri"),
    (("humanist", "warm"), "Verdana", "Calibri"),
    (("bold", "impact", "strong"), "Cambria", "Arial"),
    (("corporate", "business", "professional", "enterprise"), "Calibri", "Arial"),
    (("playful", "friendly", "casual", "fun"), "Trebuchet MS", "Verdana"),
]


def _match_score(brief_lower: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for kw in keywords if kw in brief_lower)


def pair_for_brief(brief: str, seed: int = 0) -> FontPair:
    """Deterministically map mood keywords in ``brief`` to a (heading, body) pair.

    The rule with the most keyword hits wins; ties are broken by ``seed`` so the
    same seed always yields the same pair.
    """
    lower = brief.lower()
    scores = [_match_score(lower, kw) for kw, _, _ in _FONT_RULES]
    best = max(scores) if scores else 0

    if best == 0:
        return FontPair(heading="Arial", body="Arial", heading_usage_pct=55.0, body_usage_pct=45.0)

    tied = [i for i, s in enumerate(scores) if s == best]
    chosen = tied[seed % len(tied)]
    _, heading, body = _FONT_RULES[chosen]
    return FontPair(heading=heading, body=body, heading_usage_pct=55.0, body_usage_pct=45.0)


def look_contrast(pair: FontPair) -> str:
    """Informational heading-vs-body contrast: 'high' or 'medium'."""
    if font_kind(pair.heading) == "serif" and font_kind(pair.body) == "sans":
        return "high"
    if pair.heading != pair.body:
        return "medium"
    return "medium"


def pick_fallback_font(seed: int, exclude: str) -> str:
    """A deterministic fallback family differing from ``exclude``."""
    pool = [n for n in FONT_NAMES if n != exclude]
    rng = random.Random(seed)
    return rng.choice(pool)

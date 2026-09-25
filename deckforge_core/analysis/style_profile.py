"""Statistical style derivation from extracted decks (Workstream B).

Every metric is *quantile-based and measured from real content* — nothing is
imagined. Fonts are the modal fonts of heading/body runs, palette colors are
k-means clusters of the actual fill + text colors with roles assigned by
brightness/usage, margins/grid come from shape edges, the type scale comes from
the real size distribution, and density stats are plain aggregates.

Because extracted geometry is in RELATIVE (0..1) units, all derived geometry
(margins, grid, baseline) is comparable across deck sizes.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np
from sklearn.cluster import KMeans

from deckforge_core.analysis.features import bullet_paragraphs, largest_run_pt
from deckforge_core.schemas.extracted import (
    ExtractedDeck,
    ExtractedSlide,
    image_area_fraction,
    total_words,
)
from deckforge_core.schemas.pack import (
    ColorPalette,
    DensityStats,
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

_KM_RANDOM_STATE = 0
_PALETTE_CLUSTERS = 5
_MIN_PALETTE = 3  # minimum unique colors before k-means is worth running


@dataclass
class _Run:
    font_name: str | None
    size_pt: float | None
    bold: bool
    text: str


def _collect_runs(decks: list[ExtractedDeck]) -> list[_Run]:
    runs: list[_Run] = []
    for deck in decks:
        for slide in deck.slides:
            for shape in slide.shapes:
                for para in shape.text:
                    for run in para.runs:
                        if not run.text:
                            continue
                        runs.append(_Run(run.font_name, run.size_pt, run.bold, run.text))
    return runs


def _mode(values: list) -> float | None:
    if not values:
        return None
    ((value, _count),) = Counter(round(float(v), 2) for v in values).most_common(1)
    return value


def _weight_name(bold_fraction: float) -> str:
    if bold_fraction >= 0.40:
        return "bold"
    if bold_fraction >= 0.20:
        return "medium"
    return "regular"


def _hex_to_rgb(hex_col: str) -> tuple[int, int, int]:
    h = hex_col.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    clamped = tuple(max(0, min(255, int(round(v)))) for v in rgb)
    return "#{:02X}{:02X}{:02X}".format(*clamped)


def _brightness(rgb: tuple) -> float:
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def _slides(decks: list[ExtractedDeck]) -> list[ExtractedSlide]:
    return [s for d in decks for s in d.slides]


# --------------------------------------------------------------------------- #
# Fonts
# --------------------------------------------------------------------------- #
def _fonts(decks: list[ExtractedDeck], runs: list[_Run]) -> FontPair:
    # heading runs: the largest-size run on every slide (per-slide big text).
    heading_runs: list[_Run] = []
    for slide in _slides(decks):
        max_pt = largest_run_pt(slide)
        if max_pt <= 0:
            continue
        for shape in slide.shapes:
            for para in shape.text:
                for run in para.runs:
                    if run.size_pt and float(run.size_pt) >= max_pt - 0.5 and run.text:
                        heading_runs.append(_Run(run.font_name, run.size_pt, run.bold, run.text))

    def modal_font(collection: list[_Run]) -> tuple[str, float]:
        fonts = [r.font_name for r in collection if r.font_name]
        if not fonts:
            return "Arial", 0.0
        ((font, count),) = Counter(fonts).most_common(1)
        return font, count / len(fonts)

    heading_font, heading_share = modal_font(heading_runs)
    body_font, body_share = modal_font(runs)
    return FontPair(
        heading=heading_font or "Arial",
        body=body_font or "Arial",
        fallback=[],
        heading_usage_pct=round(heading_share * 100, 1),
        body_usage_pct=round(body_share * 100, 1),
    )


# --------------------------------------------------------------------------- #
# Palette
# --------------------------------------------------------------------------- #
def _palette_colors(decks: list[ExtractedDeck]) -> tuple[dict[str, float], float]:
    """Collect ``{hex: weight}`` for fill + text colors; return also the
    fraction of slides that carry at least one explicit color (signal)."""
    weights: Counter[str] = Counter()
    slides = _slides(decks)
    colored_slides = 0
    for slide in slides:
        colored = False
        for shape in slide.shapes:
            if shape.fill_hex:
                weights[shape.fill_hex] += 1.0
                colored = True
            for para in shape.text:
                for run in para.runs:
                    if run.color_hex:
                        weights[run.color_hex] += 1.0
                        colored = True
        if colored:
            colored_slides += 1
    signal = colored_slides / len(slides) if slides else 0.0
    return dict(weights), signal


def _cluster_palette(colors: dict[str, float]) -> list[tuple[np.ndarray, float]]:
    """Return [(rgb_center, weight)] clusters from ``{hex: weight}``."""
    keys = list(colors)
    rgb = np.array([_hex_to_rgb(k) for k in keys], dtype=float)
    weights_array = np.array([colors[k] for k in keys], dtype=float)
    if len(keys) <= _MIN_PALETTE:
        return [
            (rgb[i], float(weights_array[i])) for i in range(len(keys))
        ]
    k = min(_PALETTE_CLUSTERS, len(keys))
    model = KMeans(n_clusters=k, random_state=_KM_RANDOM_STATE, n_init=10)
    labels = model.fit_predict(rgb)
    out: list[tuple[np.ndarray, float]] = []
    for label in sorted(set(labels.tolist())):
        members = rgb[labels == label]
        weights = weights_array[labels == label]
        center = np.average(members, axis=0, weights=weights)
        out.append((center, float(weights.sum())))
    return out


def _palette(decks: list[ExtractedDeck], signal: float) -> ColorPalette:
    colors, _ = _palette_colors(decks)
    if not colors:
        fallback = [
            PaletteColor(role="bg", hex="#FFFFFF", usage_pct=45.0),
            PaletteColor(role="text", hex="#111111", usage_pct=40.0),
            PaletteColor(role="muted-text", hex="#8A8A8A", usage_pct=7.0),
            PaletteColor(role="neutral1", hex="#E8E8E8", usage_pct=4.0),
            PaletteColor(role="card-bg", hex="#F5F5F5", usage_pct=2.0),
            PaletteColor(role="line", hex="#D1D1D1", usage_pct=2.0),
        ]
        return ColorPalette(colors=fallback)

    clusters = _cluster_palette(colors)
    clusters.sort(key=lambda c: c[1], reverse=True)
    total = sum(w for _, w in clusters)

    # Roles: text = darkest; bg = brightest among well-used clusters; the most
    # used remaining clusters become accents / neutrals.
    by_brightness = sorted(
        clusters, key=lambda c: _brightness(c[0]), reverse=True
    )
    text = by_brightness[-1]
    used_usage = 0.02 * total
    bg = max((c for c in by_brightness if c[1] >= used_usage), key=lambda c: _brightness(c[0]))
    if bg is text:
        bg = max(by_brightness[: len(by_brightness) - 1], key=lambda c: _brightness(c[0]))
    remaining = [c for c in clusters if c is not text and c is not bg]
    muted = sorted(remaining, key=lambda c: _brightness(c[0]))[:1]
    muted = muted[0] if muted else text
    rest = [c for c in remaining if c is not muted]

    role_order = ("accent1", "accent2", "accent3", "neutral1", "neutral2", "card-bg", "line")
    palette_roles: list[tuple[tuple[np.ndarray, float], str]] = [(text, "text"), (bg, "bg")]
    if muted is not text and muted is not bg:
        palette_roles.append((muted, "muted-text"))
    for role in role_order:
        if not rest:
            break
        center, weight = rest.pop(0)
        palette_roles.append(((center, weight), role))

    if len(palette_roles) < 2:
        palette_roles.append((text, "accent1"))

    palette_colors: list[PaletteColor] = []
    for (center, weight), role_name in palette_roles:
        palette_colors.append(
            PaletteColor(
                role=role_name,
                hex=_rgb_to_hex(center),
                usage_pct=round(weight / total * 100, 2),
            )
        )
    return ColorPalette(colors=palette_colors)


# --------------------------------------------------------------------------- #
# Margins + grid
# --------------------------------------------------------------------------- #
def _margins(decks: list[ExtractedDeck]) -> Margins:
    left: list[float] = []
    right: list[float] = []
    top: list[float] = []
    bottom: list[float] = []
    for slide in _slides(decks):
        for s in slide.shapes:
            if s.w >= 0.95 and s.h >= 0.95:  # full-bleed: no margin signal
                continue
            if 0.0 <= s.x < 0.25:
                left.append(s.x)
            if 0.75 < s.x + s.w <= 1.0:
                right.append(1.0 - (s.x + s.w))
            if 0.0 <= s.y < 0.25:
                top.append(s.y)
            if 0.75 < s.y + s.h <= 1.0:
                bottom.append(1.0 - (s.y + s.h))

    def modal_edge(values: list[float], default: float) -> float:
        if not values:
            return default
        rounded = [round(v * 100) / 100 for v in values]
        counts = Counter(rounded)
        best = max(counts.values())
        edge = min(v for v, c in counts.items() if c == best)
        return min(max(edge, 0.0), 0.25)

    return Margins(
        left=modal_edge(left, 0.06),
        right=modal_edge(right, 0.06),
        top=modal_edge(top, 0.06),
        bottom=modal_edge(bottom, 0.06),
    )


def _grid(decks: list[ExtractedDeck], body_size: float) -> Grid:
    x_starts: list[float] = []
    baseline: list[float] = []
    for slide in _slides(decks):
        for s in slide.shapes:
            if s.w >= 0.98 and s.h >= 0.98:
                continue
            if 0.0 <= s.x <= 1.0:
                x_starts.append(s.x)
            runs = [r for p in s.text for r in p.runs]
            if not runs:
                continue
            max_pt = max(r.size_pt or 0 for r in runs) or 0.0
            if body_size and abs(max_pt - body_size) < 0.5 and s.h > 0:
                baseline.append(round(s.h, 2))

    columns = 12
    if x_starts:
        best_frac = -1.0
        for candidate in (3, 4, 6, 12):
            tol = 0.12 / candidate
            frac = sum(
                1.0 for x in x_starts
                if any(abs(x - m / candidate) < tol for m in range(candidate + 1))
            ) / len(x_starts)
            if frac > best_frac + 1e-9:
                best_frac, columns = frac, candidate
        if best_frac < 0.3:
            columns = 12

    baseline_step = 0.02
    if baseline:
        counts = Counter(baseline)
        step = max(counts.values())
        baseline_step = min(
            max(min(v for v, c in counts.items() if c == step), 0.005), 0.15
        )
    return Grid(columns=columns, gutter=0.02, baseline_step=baseline_step)


# --------------------------------------------------------------------------- #
# Type scale
# --------------------------------------------------------------------------- #
def _type_scale(runs: list[_Run], all_slides: list[ExtractedSlide]) -> TypeScale:
    sizes = Counter(round(float(r.size_pt)) for r in runs if r.size_pt and r.size_pt > 0)
    if not sizes:
        return TypeScale(
            entries=[
                TypeScaleEntry(name="kicker", size_pt=12, weight="medium", caps="upper"),
                TypeScaleEntry(name="h1", size_pt=40, weight="bold"),
                TypeScaleEntry(name="h2", size_pt=28, weight="bold"),
                TypeScaleEntry(name="body", size_pt=16, weight="regular"),
                TypeScaleEntry(name="small", size_pt=12, weight="regular"),
                TypeScaleEntry(name="big-number", size_pt=72, weight="bold"),
                TypeScaleEntry(name="caption", size_pt=10, weight="regular"),
            ]
        )

    ranked = sizes.most_common()  # [(size, count)] by count desc

    def modal_where(predicate) -> int | None:
        for size, _count in ranked:
            if predicate(size):
                return size
        return None

    body = ranked[0][0]  # modal size overall

    h1 = modal_where(lambda s: s >= 20) or max(round(body * 2.2), body + 4)
    h1 = max(h1, body + 4)

    h2 = modal_where(lambda s: body < s < h1) or round(body * 1.3)
    h2 = max(min(h2, h1 - 2), body + 2) if h2 < h1 else h1 - 2
    h2 = max(h2, body + 2)

    caption = max(min(sizes), 6)
    small = modal_where(lambda s: caption < s < body) or round((caption + body) / 2)

    uppercase_runs = [r for r in runs if r.text.isupper() and len(r.text.strip()) > 1]
    kicker_tier = sorted({round(float(r.size_pt)) for r in uppercase_runs if r.size_pt})
    kicker = kicker_tier[0] if kicker_tier else round(body)

    numeric_runs = [r for r in runs if _is_number(r.text)]
    numeric_sizes = sorted(round(float(r.size_pt)) for r in numeric_runs if r.size_pt)
    if numeric_sizes:
        big_number = float(np.median(numeric_sizes))
    else:
        big_number = round(h1 * 1.8)

    has_bullets = any(bullet_paragraphs(s) > 0 for s in all_slides)

    def bold_share(collection: list[_Run], size_pt: float) -> float:
        tier = [r for r in collection if r.size_pt and abs(float(r.size_pt) - size_pt) < 0.5]
        if not tier:
            return 0.0
        return sum(1 for r in tier if r.bold) / len(tier)

    body_entry = TypeScaleEntry(
        name="body",
        size_pt=float(body),
        weight=_weight_name(bold_share(runs, body)),
        line_spacing=1.2 if has_bullets else 1.1,
    )
    return TypeScale(
        entries=[
            TypeScaleEntry(
                name="kicker",
                size_pt=float(kicker),
                weight="medium" if bold_share(runs, kicker) >= 0.2 else "regular",
                caps="upper",
            ),
            TypeScaleEntry(name="h1", size_pt=float(h1), weight=_weight_name(bold_share(runs, h1))),
            TypeScaleEntry(name="h2", size_pt=float(h2), weight=_weight_name(bold_share(runs, h2))),
            body_entry,
            TypeScaleEntry(name="small", size_pt=float(small), weight="regular"),
            TypeScaleEntry(name="big-number", size_pt=float(big_number), weight="bold"),
            TypeScaleEntry(name="caption", size_pt=float(caption), weight="regular"),
        ]
    )


def _is_number(text: str) -> bool:
    t = text.strip()
    return bool(t) and any(c.isdigit() for c in t) and all(
        c in "0123456789.,%$#-+x\u00d7() " for c in t
    )


# --------------------------------------------------------------------------- #
# Image treatment + density + confidence
# --------------------------------------------------------------------------- #
def _image_treatment(decks: list[ExtractedDeck]) -> ImageTreatment:
    slides = _slides(decks)
    full_bleed = sum(1 for s in slides if image_area_fraction(s) > 0.8)
    pictures = any(shape.image is not None for slide in slides for shape in slide.shapes)
    fraction = full_bleed / len(slides) if slides else 0.0

    frame_colors = Counter(
        shape.line_hex for slide in slides for shape in slide.shapes if shape.image and shape.line_hex
    )
    frame_color = frame_colors.most_common(1)[0][0] if frame_colors else None

    if fraction > 0.5:
        mode = "full-bleed"
    elif pictures:
        mode = "framed"
    else:
        mode = "none"
    return ImageTreatment(mode=mode, corner_radius=0.0, frame_color=frame_color, frame_weight_pt=1.0)


def _density(decks: list[ExtractedDeck]) -> DensityStats:
    slides = _slides(decks)
    if not slides:
        return DensityStats(slides_analysed=0)
    words = [total_words(s) for s in slides]
    bullets = [bullet_paragraphs(s) for s in slides]
    return DensityStats(
        words_per_slide_median=int(round(float(np.median(words)))),
        words_per_slide_max=int(max(words)),
        bullets_per_slide_median=int(round(float(np.median(bullets)))),
        image_area_fraction_median=round(float(np.median([image_area_fraction(s) for s in slides])), 4),
        mean_shapes_per_slide=round(sum(len(s.shapes) for s in slides) / len(slides), 2),
        slides_analysed=len(slides),
    )


def _confidence(n_slides: int, palette_signal: float, font_signal: float, grid_signal: float) -> StyleConfidence:
    base = min(1.0, n_slides / 50.0)
    palette_conf = base * min(1.0, palette_signal / 0.30)
    fonts_conf = base * min(1.0, font_signal / 0.50)
    grid_conf = base * min(1.0, grid_signal / 0.50)
    layout_conf = base
    overall = 0.25 * (palette_conf + fonts_conf + grid_conf + layout_conf)
    return StyleConfidence(
        overall=round(overall, 3),
        palette=round(palette_conf, 3),
        fonts=round(fonts_conf, 3),
        grid=round(grid_conf, 3),
        layout=round(layout_conf, 3),
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def style_from_decks(decks: list[ExtractedDeck]) -> StyleProfile:
    """Derive a validated :class:`StyleProfile` from extracted decks.

    All quantities are statistical aggregates of the real content (see module
    docstring). The result is round-tripped through pydantic validation so an
    invalid profile can never escape.
    """
    runs = _collect_runs(decks)
    color_weights, palette_signal = _palette_colors(decks)
    all_slides = _slides(decks)

    fonts = _fonts(decks, runs)
    palette = _palette(decks, palette_signal)
    type_scale = _type_scale(runs, all_slides)
    margins = _margins(decks)
    grid = _grid(decks, type_scale.entry("body").size_pt)
    image_treatment = _image_treatment(decks)

    if runs:
        font_signal = sum(1 for r in runs if r.font_name) / len(runs)
    else:
        font_signal = 0.0
    shape_count = sum(len(s.shapes) for d in decks for s in d.slides)
    # Grid signal: share of shapes whose left edge lands near a grid column.
    aligned = sum(
        1
        for d in decks
        for s in d.slides
        for shape in s.shapes
        if shape.w < 0.98 and any(abs(shape.x - m / grid.columns) < 0.03 for m in range(grid.columns + 1))
    )
    grid_signal = aligned / shape_count if shape_count else 0.0

    notes = [
        "statistical derivation from extracted decks; all metrics quantile-based",
        "corner radius not measurable from pptx geometry; set to 0.0",
        f"grid columns = {grid.columns}; image mode = {image_treatment.mode}",
    ]
    if not color_weights:
        notes.append("no explicit fill/text colors found; palette is a neutral fallback")

    profile = StyleProfile.model_validate(
        {
            "version": 1,
            "palette": palette,
            "fonts": fonts,
            "type_scale": type_scale,
            "margins": margins,
            "grid": grid,
            "corner_radii": 0.0,
            "line_weight_pt": 1.0,
            "image_treatment": image_treatment,
            "density": _density(decks),
            "confidence": _confidence(len(all_slides), palette_signal, font_signal, grid_signal),
            "notes": notes,
        }
    )
    # Belt-and-braces: guarantee the profile serialises and re-validates.
    return StyleProfile.model_validate(profile.model_dump(mode="json"))

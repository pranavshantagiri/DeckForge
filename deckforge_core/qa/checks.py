"""Deterministic, declaratively-pure QA checks.

Each check takes explicit inputs (never module state), re-uses the renderer's
own geometry math (Workstream C) so findings reproduce offline, and returns
``list[QAIssue]``. Run them all via :func:`run_deterministic`.
"""

from __future__ import annotations

from typing import Optional, Sequence

from deckforge_core.renderer.canvas import canvas_size
from deckforge_core.renderer.textfit import estimate_block_height, fit_paragraphs
from deckforge_core.schemas.blueprints import BlueprintLibrary, ContentKind, SlotDef
from deckforge_core.schemas.deck_plan import DeckPlan, SlotValue
from deckforge_core.schemas.pack import StyleProfile
from deckforge_core.schemas.qa import IssueSeverity, QACheckType, QAIssue

# Banned phrase list embedded locally because Workstream D's planner lint does
# not exist yet; merge point with planner/lint.py when that lands.
BANNED_PHRASES: tuple[str, ...] = (
    "lorem ipsum",
    "xxx",
    "todo",
    "tbd",
    "tba",
    "coming soon",
)

_BULLET_CHARS = ("•", "-", "–", "▪", "●", "*", "‣")

MIN_FONT_PT = 8.0
OFF_GRID_TOLERANCE = 0.005
OVERLAP_AREA_FRACTION = 0.05


# --------------------------------------------------------------------------- #
# WCAG contrast math (local, pure copy of the standard formula)
# --------------------------------------------------------------------------- #
def _hex_channels(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _linearize(channel: int) -> float:
    component = channel / 255.0
    if component <= 0.04045:
        return component / 12.92
    return ((component + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    """WCAG 2.x relative luminance of ``#RRGGBB`` (0.0 .. 1.0)."""
    red, green, blue = _hex_channels(hex_color)
    return (
        0.2126 * _linearize(red)
        + 0.7152 * _linearize(green)
        + 0.0722 * _linearize(blue)
    )


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    """WCAG contrast ratio between two hex colours (always >= 1.0)."""
    lighter = max(relative_luminance(hex_a), relative_luminance(hex_b))
    darker = min(relative_luminance(hex_a), relative_luminance(hex_b))
    return (lighter + 0.05) / (darker + 0.05)


# --------------------------------------------------------------------------- #
# Shared geometry helpers (mirror Workstream C's engine math)
# --------------------------------------------------------------------------- #
def _style_entry(pack: StyleProfile, name: str) -> Optional:
    try:
        return pack.type_scale.entry(name)
    except KeyError:
        return None


def _role_hex(pack: StyleProfile, role: str) -> Optional[str]:
    try:
        return pack.palette.hex(role)
    except KeyError:
        return None


def _effective_slots(library, archetype: str, aspect: str) -> list:
    try:
        _blueprint, slots = library.resolve(archetype, aspect)
    except KeyError:
        return []
    return slots


def _rendered_texts(slot_def: SlotDef, value: SlotValue) -> list[str]:
    """The strings the renderer would draw into ``slot_def`` (engine mirror)."""
    texts: list[str] = []
    bullet = ContentKind.LIST in slot_def.kinds

    def _bullet(text: str) -> str:
        text = text.strip()
        if bullet and text and not text.startswith(_BULLET_CHARS):
            return f"• {text}"
        return text

    if value.number is not None:
        texts.append(str(value.number))
    if value.text:
        texts.append(value.text)
    for paragraph in value.paragraphs or []:
        texts.append(paragraph)
    for item in value.items or []:
        texts.append(_bullet(item))
    if value.source:
        texts.append(value.source)
    return texts


def _is_text_bearing(slot_def: SlotDef, value: SlotValue) -> bool:
    if value.chart is not None or value.table is not None or value.diagram is not None:
        return False
    if value.people:
        return False
    if ContentKind.IMAGE in slot_def.kinds and (value.image is not None or value.url):
        return False
    return True


def _box_size(slot_def: SlotDef, pack: StyleProfile, canvas_w: int, canvas_h: int) -> tuple[int, int]:
    """Text box EMU size after the pack's internal margin insets (engine mirror)."""
    region_w = round(slot_def.region.w * canvas_w)
    region_h = round(slot_def.region.h * canvas_h)
    inset_x = round((pack.margins.left + pack.margins.right) * region_w)
    inset_y = round((pack.margins.top + pack.margins.bottom) * region_h)
    return max(1, region_w - inset_x), max(1, region_h - inset_y)


def text_overflows(
    pack: StyleProfile,
    slot_def: SlotDef,
    value: SlotValue,
    canvas_w: int,
    canvas_h: int,
) -> bool:
    """True when ``value`` would overflow the slot even after shrink-to-fit."""
    texts = _rendered_texts(slot_def, value)
    if not texts:
        return False
    entry = _style_entry(pack, slot_def.style)
    if entry is None:
        return False
    box_w, box_h = _box_size(slot_def, pack, canvas_w, canvas_h)
    try:
        _size, overflow, _lines = fit_paragraphs(texts, entry, box_w, box_h)
    except Exception:
        return False
    return bool(overflow)


def _first_slide_n(slides_plan: DeckPlan) -> int:
    if slides_plan is not None and slides_plan.slides:
        return slides_plan.slides[0].n
    return 1


def _intersection_area(a, b) -> float:
    x0, x1 = max(a.x, b.x), min(a.x + a.w, b.x + b.w)
    y0, y1 = max(a.y, b.y), min(a.y + a.h, b.y + b.h)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


# --------------------------------------------------------------------------- #
# Individual checks
# --------------------------------------------------------------------------- #
def check_overflow(
    pack: StyleProfile,
    slides_plan: DeckPlan,
    blueprint_library: BlueprintLibrary,
) -> list[QAIssue]:
    """Text that still overflows its region after shrink-to-fit -> ERROR."""
    issues: list[QAIssue] = []
    aspect = slides_plan.aspect_ratio or "16:9"
    canvas_w, canvas_h = canvas_size(aspect)
    for slide in slides_plan.slides:
        for slot_def in _effective_slots(blueprint_library, slide.archetype, aspect):
            value = slide.slots.get(slot_def.name)
            if value is None or value.is_empty:
                continue
            if not _is_text_bearing(slot_def, value):
                continue
            if not text_overflows(pack, slot_def, value, canvas_w, canvas_h):
                continue
            texts = _rendered_texts(slot_def, value)
            entry = _style_entry(pack, slot_def.style)
            box_w, box_h = _box_size(slot_def, pack, canvas_w, canvas_h)
            estimated = (
                estimate_block_height(
                    "\n".join(texts), entry.size_pt, box_w, entry.line_spacing
                )
                if entry is not None
                else 0
            )
            issues.append(
                QAIssue(
                    check=QACheckType.OVERFLOW,
                    severity=IssueSeverity.ERROR,
                    slide_n=slide.n,
                    message=(
                        f"slide {slide.n} slot {slot_def.name!r}: text overflows "
                        "its region even shrunk to the minimum size"
                    ),
                    detail={
                        "slot": slot_def.name,
                        "estimated_height_emu": estimated,
                        "region_height_emu": box_h,
                    },
                    fix="shorten text / reduce copy",
                )
            )
    return issues


def check_overlap(
    pack: StyleProfile,
    slides_plan: DeckPlan,
    blueprint_library: BlueprintLibrary,
) -> list[QAIssue]:
    """Two occupied regions sharing more than 5% of the smaller area -> ERROR."""
    issues: list[QAIssue] = []
    aspect = slides_plan.aspect_ratio or "16:9"
    for slide in slides_plan.slides:
        slots = _effective_slots(blueprint_library, slide.archetype, aspect)
        occupied = [
            s
            for s in slots
            if (value := slide.slots.get(s.name)) is not None and not value.is_empty
        ]
        for index, first in enumerate(occupied):
            for second in occupied[index + 1 :]:
                overlap = _intersection_area(first.region, second.region)
                if overlap <= OVERLAP_AREA_FRACTION * min(
                    first.region.w * first.region.h, second.region.w * second.region.h
                ):
                    continue
                issues.append(
                    QAIssue(
                        check=QACheckType.OVERLAP,
                        severity=IssueSeverity.ERROR,
                        slide_n=slide.n,
                        message=(
                            f"slide {slide.n} slots {first.name!r} and {second.name!r} "
                            "overlap by more than 5% of their areas"
                        ),
                        detail={
                            "slots": [first.name, second.name],
                            "overlap_area": round(overlap, 4),
                        },
                        fix="move one region clear of the other",
                    )
                )
    return issues


def check_off_grid(
    pack: StyleProfile,
    slides_plan: DeckPlan,
    blueprint_library: BlueprintLibrary,
) -> list[QAIssue]:
    """Occupied region not aligned to the pack's column grid -> WARNING."""
    issues: list[QAIssue] = []
    grid = pack.grid
    margins = pack.margins
    total = 1.0 - margins.left - margins.right - (grid.columns - 1) * grid.gutter
    col_w = total / grid.columns
    if col_w <= 0:
        return issues
    stride = col_w + grid.gutter
    lefts = [margins.left + i * stride for i in range(grid.columns)]
    widths = [k * col_w + (k - 1) * grid.gutter for k in range(1, grid.columns + 1)]
    tolerance = OFF_GRID_TOLERANCE

    aspect = slides_plan.aspect_ratio or "16:9"
    for slide in slides_plan.slides:
        slots = _effective_slots(blueprint_library, slide.archetype, aspect)
        occupied = [
            s
            for s in slots
            if (value := slide.slots.get(s.name)) is not None and not value.is_empty
        ]
        for slot_def in occupied:
            if slot_def.region.w < 2 * col_w - tolerance:
                continue  # only component-width boxes (>= 2 columns)
            x_ok = any(abs(slot_def.region.x - left) <= tolerance for left in lefts)
            w_ok = any(abs(slot_def.region.w - w) <= tolerance for w in widths)
            if x_ok and w_ok:
                continue
            issues.append(
                QAIssue(
                    check=QACheckType.OFF_GRID,
                    severity=IssueSeverity.WARNING,
                    slide_n=slide.n,
                    message=(
                        f"slide {slide.n} slot {slot_def.name!r} is off the pack "
                        f"grid (x={slot_def.region.x:.3f}, w={slot_def.region.w:.3f})"
                    ),
                    detail={
                        "slot": slot_def.name,
                        "x": round(slot_def.region.x, 4),
                        "w": round(slot_def.region.w, 4),
                    },
                    fix="align the region to the pack's column grid",
                )
            )
    return issues


def _is_large(entry) -> bool:
    return entry.size_pt >= 18 or (entry.size_pt >= 14 and entry.weight == "bold")


def _text_role_for_entry(entry_name: str) -> str:
    if entry_name in ("number", "big-number", "kicker"):
        return "accent1"
    if entry_name in ("caption", "small"):
        return "muted-text"
    return "text"


def check_contrast(pack: StyleProfile, slides_plan: Optional[DeckPlan] = None) -> list[QAIssue]:
    """Low WCAG contrast between text roles and the background -> WARNING."""
    issues: list[QAIssue] = []
    background = _role_hex(pack, "bg")
    if background is None:
        return issues
    slide_n = _first_slide_n(slides_plan or DeckPlan(pack="", slides=[]))
    seen: set[tuple[str, str]] = set()
    for entry in pack.type_scale.entries:
        role = _text_role_for_entry(entry.name)
        foreground = _role_hex(pack, role)
        if foreground is None:
            continue
        pair = (foreground, background)
        if pair in seen:
            continue
        seen.add(pair)
        ratio = contrast_ratio(foreground, background)
        threshold = 3.0 if _is_large(entry) else 4.5
        if ratio < threshold:
            issues.append(
                QAIssue(
                    check=QACheckType.CONTRAST,
                    severity=IssueSeverity.WARNING,
                    slide_n=slide_n,
                    message=(
                        f"slide {slide_n}: {role!r} ({foreground}) on bg "
                        f"({background}) is {ratio:.2f}:1, below {threshold:g}:1"
                    ),
                    detail={
                        "role": role,
                        "foreground": foreground,
                        "background": background,
                        "ratio": round(ratio, 2),
                        "threshold": threshold,
                    },
                    fix="pick a darker or lighter palette colour for this role",
                )
            )
    return issues


def _slot_styles(
    slides_plan: DeckPlan,
    archetype: str,
    library: Optional[BlueprintLibrary],
) -> dict[str, str]:
    if library is None:
        return {}
    return {
        slot.name: slot.style
        for slot in _effective_slots(library, archetype, slides_plan.aspect_ratio or "16:9")
    }


def check_min_font(
    pack: StyleProfile,
    slides_plan: DeckPlan,
    library: Optional[BlueprintLibrary] = None,
) -> list[QAIssue]:
    """Occupied slot styled below the minimum readable size -> WARNING."""
    issues: list[QAIssue] = []
    for slide in slides_plan.slides:
        styles = _slot_styles(slides_plan, slide.archetype, library)
        for name, value in slide.slots.items():
            if value is None or value.is_empty:
                continue
            entry = _style_entry(pack, styles.get(name, ""))
            if entry is None or entry.size_pt >= MIN_FONT_PT:
                continue
            issues.append(
                QAIssue(
                    check=QACheckType.MIN_FONT,
                    severity=IssueSeverity.WARNING,
                    slide_n=slide.n,
                    message=(
                        f"slide {slide.n} slot {name!r} style {entry.name!r} is "
                        f"{entry.size_pt:g}pt, below the {MIN_FONT_PT:g}pt minimum"
                    ),
                    detail={"slot": name, "size_pt": entry.size_pt},
                    fix="raise the type-scale size for this slot style",
                )
            )
    return issues


def check_empty_placeholders(
    pack: StyleProfile,
    slides_plan: DeckPlan,
    blueprint_library: BlueprintLibrary,
) -> list[QAIssue]:
    """Required slot left empty by the plan -> WARNING."""
    issues: list[QAIssue] = []
    aspect = slides_plan.aspect_ratio or "16:9"
    for slide in slides_plan.slides:
        for slot_def in _effective_slots(blueprint_library, slide.archetype, aspect):
            value = slide.slots.get(slot_def.name)
            if (value is not None and not value.is_empty) or slot_def.optional:
                continue
            issues.append(
                QAIssue(
                    check=QACheckType.EMPTY_PLACEHOLDER,
                    severity=IssueSeverity.WARNING,
                    slide_n=slide.n,
                    message=(
                        f"slide {slide.n} required slot {slot_def.name!r} has no content"
                    ),
                    detail={"slot": slot_def.name, "optional": slot_def.optional},
                    fix="provide content for this slot",
                )
            )
    return issues


def check_palette(pack: StyleProfile, colors: Sequence[str] = ()) -> list[QAIssue]:
    """Colors outside the palette (renderer constrains these; vision feeds this)."""
    issues: list[QAIssue] = []
    palette = {color.hex.lower() for color in pack.palette.colors}
    for color in colors:
        if color.lower() in palette:
            continue
        issues.append(
            QAIssue(
                check=QACheckType.OFF_PALETTE,
                severity=IssueSeverity.INFO,
                slide_n=1,
                message=f"colour {color} is not in the pack palette",
                detail={"colour": color},
                fix="use a palette colour",
            )
        )
    return issues


def check_banned_phrases(slides_plan: DeckPlan) -> list[QAIssue]:
    """Copy that still contains throwaway placeholder phrases -> INFO."""
    issues: list[QAIssue] = []
    for slide in slides_plan.slides:
        chunks: list[Optional[str]] = [slide.title]
        for value in slide.slots.values():
            chunks += [value.text, value.source]
            chunks += value.paragraphs or []
            chunks += value.items or []
            if value.number is not None:
                chunks.append(str(value.number))
        haystack = "\n".join(chunk for chunk in chunks if chunk).lower()
        for phrase in BANNED_PHRASES:
            if phrase in haystack:
                issues.append(
                    QAIssue(
                        check=QACheckType.BANNED_PHRASE,
                        severity=IssueSeverity.INFO,
                        slide_n=slide.n,
                        message=f"slide {slide.n} contains banned phrase {phrase!r}",
                        detail={"phrase": phrase},
                        fix="replace with final copy",
                    )
                )
                break
    return issues


# --------------------------------------------------------------------------- #
# Fan-in
# --------------------------------------------------------------------------- #
def run_deterministic(
    pack: StyleProfile,
    slides_plan: DeckPlan,
    library: BlueprintLibrary,
) -> dict[int, list[QAIssue]]:
    """Run every deterministic check; return issues grouped by slide number."""
    all_issues = (
        check_overflow(pack, slides_plan, library)
        + check_overlap(pack, slides_plan, library)
        + check_off_grid(pack, slides_plan, library)
        + check_contrast(pack, slides_plan)
        + check_min_font(pack, slides_plan, library)
        + check_empty_placeholders(pack, slides_plan, library)
        + check_palette(pack)
        + check_banned_phrases(slides_plan)
    )
    grouped: dict[int, list[QAIssue]] = {}
    for issue in all_issues:
        grouped.setdefault(issue.slide_n, []).append(issue)
    for slide in slides_plan.slides:
        grouped.setdefault(slide.n, [])
    return {number: grouped[number] for number in sorted(grouped)}

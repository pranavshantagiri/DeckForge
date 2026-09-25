"""Building blueprints from representative slides (Workstream B).

For each canonical archetype present in a corpus, the most representative slide
(nearest to its own group's feature centroid) is picked and its shapes are
mapped onto canonical slot names from :mod:`slot_vocabulary`. Geometry is the
real relative (0..1) shape rectangles, clamped to the slide and snapped to a
0.01 grid. Per-slot text length limits come from the 5th..95th percentile of
real usage across *all* slides of that archetype.

Portrait alternates (``AlternateArrangement``) are emitted only when the
representative slide genuinely has side-by-side columns; the columns are
stacked vertically and secondary full-width slots are kept.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from deckforge_core.analysis.archetype import (
    columns,
    content_shapes,
    has_quote_marks,
    is_numeric_text,
)
from deckforge_core.analysis.features import _shape_max_pt, slide_features
from deckforge_core.schemas.archetypes import ARCHETYPE_LABELS, Archetype
from deckforge_core.schemas.blueprints import (
    AlternateArrangement,
    Blueprint,
    BlueprintLibrary,
    ContentKind,
    SlotDef,
    SlotRegion,
    TextLimits,
)
from deckforge_core.schemas.extracted import ExtractedSlide, total_words
from deckforge_core.schemas.pack import Margins
from deckforge_core.schemas.slot_vocabulary import has_vocabulary, slots_for

_GRID_STEP = 0.01
_PORTRAIT_GUTTER = 0.03
_HEADER_WIDTH = 0.65


@dataclass
class _MappedSlot:
    """A slide region assigned to a canonical slot."""

    name: str
    shapes: list = field(default_factory=list)
    kinds: list = field(default_factory=lambda: [ContentKind.TEXT])
    style: str = "body"
    align: str = "left"
    valign: str = "top"
    top_frac: float | None = None  # split a single parent shape: top portion
    bottom_frac: float | None = None  # split a single parent shape: bottom portion


_STYLE_BY_SLOT = {
    "title": "h1",
    "number": "big-number",
    "statement": "h1",
    "quote": "h1",
    "subtitle": "h2",
    "kicker": "kicker",
    "meta": "caption",
    "caption": "caption",
    "source": "caption",
    "author": "caption",
    "attribution": "caption",
    "thanks": "h2",
    "body": "body",
    "items": "body",
    "contact": "body",
    "col_a_body": "body",
    "col_b_body": "body",
    "col_a_heading": "h2",
    "col_b_heading": "h2",
    "left_body": "body",
    "right_body": "body",
    "left_heading": "h2",
    "right_heading": "h2",
    "left_label": "kicker",
    "right_label": "kicker",
    "card_1": "h2",
    "card_2": "h2",
    "card_3": "h2",
    "people": "body",
    "diagram": "body",
    "image": "body",
    "chart": "body",
    "table": "body",
}


# --------------------------------------------------------------------------- #
# Per-archetype slide → slot mappers (representative + usage analysis share
# these, so a slot means the same thing on every slide of an archetype).
# --------------------------------------------------------------------------- #
def _text_shapes(slide):
    return [s for s in slide.shapes if s.has_text()]


def _biggest_text(slide):
    shapes = _text_shapes(slide)
    if not shapes:
        return None
    return max(shapes, key=_shape_max_pt)


def _is_upper(text: str) -> bool:
    return len(text.strip()) > 1 and text.strip().isupper()


def _map_title(slide) -> list[_MappedSlot]:
    shapes = _text_shapes(slide)
    big = _biggest_text(slide)
    if big is None:
        return []
    slots = [_MappedSlot("title", [big], style="h1", align="left")]
    used_subtitle = False
    for s in shapes:
        if s is big:
            continue
        if _is_upper(s.text_joined()):
            slots.append(_MappedSlot("kicker", [s], style="kicker"))
        elif not used_subtitle:
            slots.append(_MappedSlot("subtitle", [s], style="h2"))
            used_subtitle = True
        else:
            slots.append(_MappedSlot("author", [s], style="caption"))
    return slots


def _map_section_divider(slide) -> list[_MappedSlot]:
    shapes = _text_shapes(slide)
    big = _biggest_text(slide)
    if big is None:
        return []
    slots = [_MappedSlot("title", [big], style="h1")]
    for s in shapes:
        if s is big:
            continue
        name = "kicker" if _is_upper(s.text_joined()) else "meta"
        slots.append(_MappedSlot(name, [s], style=_STYLE_BY_SLOT[name]))
    return slots


def _map_statement(slide) -> list[_MappedSlot]:
    shapes = _text_shapes(slide)
    big = _biggest_text(slide)
    if big is None:
        return []
    slots = [_MappedSlot("statement", [big], style="h1", align="center")]
    for s in shapes:
        if s is not big:
            slots.append(_MappedSlot("source", [s], style="caption"))
    return slots


def _map_big_number(slide) -> list[_MappedSlot]:
    shapes = _text_shapes(slide)
    numeric = [s for s in shapes if is_numeric_text(s.text_joined())]
    others = sorted(
        (s for s in shapes if s not in numeric),
        key=_shape_max_pt,
        reverse=True,
    )
    slots: list[_MappedSlot] = []
    if numeric:
        slots.append(
            _MappedSlot("number", numeric, style="big-number", align="center", valign="middle")
        )
    if others:
        slots.append(_MappedSlot("caption", [others[0]], style="caption"))
        for s in others[1:]:
            slots.append(_MappedSlot("source", [s], style="caption"))
    return slots


def _map_quote(slide) -> list[_MappedSlot]:
    shapes = _text_shapes(slide)
    quoted = [s for s in shapes if has_quote_marks(s.text_joined())]
    rest = [s for s in shapes if s not in quoted]
    slots: list[_MappedSlot] = []
    if quoted:
        slots.append(_MappedSlot("quote", quoted, style="h1", align="center"))
    for s in rest:
        slots.append(_MappedSlot("attribution", [s], style="caption"))
    return slots


def _map_chart(slide) -> list[_MappedSlot]:
    big = _biggest_text(slide)
    charts = [s for s in slide.shapes if s.shape_type == "CHART"]
    slots: list[_MappedSlot] = []
    if big is not None:
        slots.append(_MappedSlot("title", [big], style="h1"))
    if charts:
        slots.append(_MappedSlot("chart", charts, kinds=[ContentKind.CHART], style="body"))
    else:
        slots.append(
            _MappedSlot("chart", [s for s in content_shapes(slide) if s is not big], kinds=[ContentKind.CHART])
        )
    for s in _text_shapes(slide):
        if s is not big and s.word_count() <= 12:
            slots.append(_MappedSlot("source", [s], style="caption"))
    return slots


def _map_table(slide) -> list[_MappedSlot]:
    big = _biggest_text(slide)
    tables = [s for s in slide.shapes if s.shape_type == "TABLE"]
    slots: list[_MappedSlot] = []
    if big is not None:
        slots.append(_MappedSlot("title", [big], style="h1"))
    if tables:
        slots.append(_MappedSlot("table", tables, kinds=[ContentKind.TABLE], style="body"))
    for s in _text_shapes(slide):
        if s is not big and s.word_count() <= 12:
            slots.append(_MappedSlot("source", [s], style="caption"))
    return slots


def _map_full_bleed(slide) -> list[_MappedSlot]:
    pics = [s for s in slide.shapes if s.image is not None]
    shapes = _text_shapes(slide)
    big = _biggest_text(slide)
    slots: list[_MappedSlot] = []
    if pics:
        slots.append(_MappedSlot("image", pics, kinds=[ContentKind.IMAGE]))
    if big is not None:
        slots.append(_MappedSlot("title", [big], style="h1"))
    for s in shapes:
        if s is not big:
            slots.append(_MappedSlot("caption", [s], style="caption"))
    return slots


def _map_image_side(slide) -> list[_MappedSlot]:
    pics = [s for s in slide.shapes if s.image is not None]
    shapes = _text_shapes(slide)
    big = _biggest_text(slide)
    slots: list[_MappedSlot] = []
    if pics:
        slots.append(_MappedSlot("image", pics, kinds=[ContentKind.IMAGE]))
    if big is not None:
        slots.append(_MappedSlot("title", [big], style="h1"))
    body = [s for s in shapes if s is not big and s.word_count() >= 7]
    source = [s for s in shapes if s is not big and s.word_count() < 7]
    if body:
        slots.append(_MappedSlot("body", body, style="body"))
    if source:
        slots.append(_MappedSlot("source", source, style="caption"))
    return slots


def _map_three_cards(slide) -> list[_MappedSlot]:
    slots: list[_MappedSlot] = []
    big = _biggest_text(slide)
    if big is not None and big.w >= _HEADER_WIDTH:
        slots.append(_MappedSlot("title", [big], style="h1"))
    cols = columns(slide)
    cards = sorted((c[0] for c in cols if c), key=lambda s: s.x)
    for i, card in enumerate(cards[:3], start=1):
        slots.append(_MappedSlot(f"card_{i}", [card], style=_STYLE_BY_SLOT[f"card_{i}"]))
    return slots


def _column_slots(cols, names: tuple[str, str], require_headings: bool) -> list[_MappedSlot]:
    """Map a two-column slide onto ``(left, right)`` slot name pairs."""
    out: list[_MappedSlot] = []
    for side, col in zip(names, cols[:2]):
        col_text = sorted((s for s in col if s.has_text()), key=lambda s: s.y)
        if not col_text:
            continue
        first = col_text[0]
        paras = [p for p in first.text if p.text().strip()]
        lead_words = paras[0].word_count() if paras else 0
        heading_like = lead_words <= 10 and (len(paras) >= 2 or _shape_max_pt(first) >= 15)
        if heading_like:
            if len(paras) >= 2 and len(col_text) == 1:
                out.append(_MappedSlot(f"{side}_heading", [first], top_frac=0.45))
                out.append(_MappedSlot(f"{side}_body", [first], bottom_frac=0.55))
            else:
                out.append(_MappedSlot(f"{side}_heading", [first]))
                rest = col_text[1:]
                if rest:
                    out.append(_MappedSlot(f"{side}_body", rest))
        elif require_headings:
            continue
        else:
            out.append(_MappedSlot(f"{side}_body", col_text))
    return out


def _map_comparison(slide) -> list[_MappedSlot]:
    slots: list[_MappedSlot] = []
    big = _biggest_text(slide)
    if big is not None and big.w >= _HEADER_WIDTH:
        slots.append(_MappedSlot("title", [big], style="h1"))
    cols = columns(slide)
    slots.extend(_column_slots(cols, ("left", "right"), require_headings=True))
    return slots


def _map_two_column(slide) -> list[_MappedSlot]:
    slots: list[_MappedSlot] = []
    big = _biggest_text(slide)
    if big is not None and big.w >= _HEADER_WIDTH:
        slots.append(_MappedSlot("kicker", [big], style="kicker"))
    cols = columns(slide)
    slots.extend(_column_slots(cols, ("col_a", "col_b"), require_headings=False))
    return slots


def _map_agenda(slide) -> list[_MappedSlot]:
    shapes = _text_shapes(slide)
    list_shape = next(
        (s for s in shapes if len([p for p in s.text if p.text().strip()]) >= 3), None
    )
    rest = [s for s in shapes if s is not list_shape]
    slots: list[_MappedSlot] = []
    if rest:
        big = max(rest, key=_shape_max_pt)
        slots.append(_MappedSlot("kicker", [big], style="kicker"))
    items = list_shape if list_shape is not None else rest
    if items:
        slots.append(
            _MappedSlot("items", [items] if not isinstance(items, list) else items, kinds=[ContentKind.LIST])
        )
    return slots


def _map_timeline(slide) -> list[_MappedSlot]:
    big = _biggest_text(slide)
    boxes = [s for s in content_shapes(slide) if s.w >= 0.08 and s.h >= 0.03 and s is not big]
    slots: list[_MappedSlot] = []
    if big is not None:
        slots.append(_MappedSlot("title", [big], style="h1"))
    if boxes:
        slots.append(_MappedSlot("items", boxes, kinds=[ContentKind.LIST]))
    return slots


def _map_process_flow(slide) -> list[_MappedSlot]:
    shapes = _text_shapes(slide)
    big = _biggest_text(slide)
    boxes = [s for s in content_shapes(slide) if s.w >= 0.08 and s.h >= 0.03 and s is not big]
    caption = [s for s in shapes if s is not big and s.word_count() <= 16]
    slots: list[_MappedSlot] = []
    if big is not None:
        slots.append(_MappedSlot("title", [big], style="h1"))
    if boxes:
        slots.append(_MappedSlot("diagram", boxes, kinds=[ContentKind.DIAGRAM]))
    if caption:
        slots.append(_MappedSlot("caption", caption, style="caption"))
    return slots


def _map_team(slide) -> list[_MappedSlot]:
    big = _biggest_text(slide)
    cards = [c[0] for c in columns(slide) if c]
    slots: list[_MappedSlot] = []
    if big is not None and big.w >= _HEADER_WIDTH:
        slots.append(_MappedSlot("title", [big], style="h1"))
    if cards:
        slots.append(_MappedSlot("people", cards, kinds=[ContentKind.PERSON]))
    return slots


def _map_closing(slide) -> list[_MappedSlot]:
    shapes = _text_shapes(slide)
    big = _biggest_text(slide)
    slots: list[_MappedSlot] = []
    if big is not None:
        slots.append(_MappedSlot("title", [big], style="h1"))
    roles = ["kicker", "contact", "thanks"]
    idx = 0
    for s in shapes:
        if s is big:
            continue
        name = roles[min(idx, 2)]
        idx += 1
        slots.append(_MappedSlot(name, [s], style=_STYLE_BY_SLOT[name]))
    return slots


def _map_generic(slide) -> list[_MappedSlot]:
    return [
        _MappedSlot(
            "body",
            content_shapes(slide) or slide.shapes,
            kinds=[ContentKind.TEXT, ContentKind.PARAGRAPHS],
            style="body",
        )
    ]


_MAPPERS = {
    "title": _map_title,
    "section-divider": _map_section_divider,
    "statement": _map_statement,
    "big-number": _map_big_number,
    "quote": _map_quote,
    "chart": _map_chart,
    "table": _map_table,
    "full-bleed-image": _map_full_bleed,
    "image-left": _map_image_side,
    "image-right": _map_image_side,
    "three-cards": _map_three_cards,
    "comparison": _map_comparison,
    "two-column-text": _map_two_column,
    "agenda": _map_agenda,
    "timeline": _map_timeline,
    "process-flow": _map_process_flow,
    "team": _map_team,
    "closing": _map_closing,
}


def _map_slide(slide: ExtractedSlide, archetype: str) -> list[_MappedSlot]:
    mapper = _MAPPERS.get(archetype, _map_generic)
    mapped = mapper(slide)
    if not mapped:  # never emit an empty blueprint
        mapped = _map_generic(slide)
    return mapped


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #
def _snap(value: float) -> float:
    return round(value * 100) / 100


def _clamp_region(x: float, y: float, w: float, h: float) -> SlotRegion:
    w = max(min(w, 1.0 - x), 0.01)
    h = max(min(h, 1.0 - y), 0.01)
    x = min(max(x, 0.0), 1.0 - w)
    y = min(max(y, 0.0), 1.0 - h)
    return SlotRegion(
        x=_snap(x),
        y=_snap(y),
        w=_snap(w),
        h=_snap(h),
    )


def _merged_region(shapes) -> SlotRegion:
    if not shapes:
        return SlotRegion(x=0.0, y=0.0, w=1.0, h=1.0)
    x = min(s.x for s in shapes)
    y = min(s.y for s in shapes)
    right = max(s.x + s.w for s in shapes)
    bottom = max(s.y + s.h for s in shapes)
    return _clamp_region(x, y, right - x, bottom - y)


def _region_for(mapped: _MappedSlot) -> SlotRegion | None:
    if not mapped.shapes:
        return None
    if mapped.top_frac is not None:
        src = mapped.shapes[0]
        return _clamp_region(src.x, src.y, src.w, src.h * mapped.top_frac)
    if mapped.bottom_frac is not None:
        src = mapped.shapes[0]
        return _clamp_region(src.x, src.y + src.h * (1 - mapped.bottom_frac), src.w, src.h * mapped.bottom_frac)
    return _merged_region(mapped.shapes)


def _text_slot(archetype: str, mapped: _MappedSlot) -> bool:
    kinds = set(mapped.kinds)
    return bool(kinds & {ContentKind.TEXT, ContentKind.PARAGRAPHS, ContentKind.LIST, ContentKind.NUMBER})


def _kinds_for(archetype: str, name: str) -> list[ContentKind] | None:
    voc = slots_for(archetype)
    kinds = voc.kinds_for(name)
    return list(kinds) if kinds else None


def _make_slot(archetype: str, mapped: _MappedSlot, region: SlotRegion) -> SlotDef:
    kinds = _kinds_for(archetype, mapped.name) or mapped.kinds
    return SlotDef(
        name=mapped.name,
        label=mapped.name,
        kinds=kinds,
        region=region,
        align=mapped.align,
        valign=mapped.valign,
        style=mapped.style,
        optional=True,
    )


# --------------------------------------------------------------------------- #
# Text limits + word totals from real usage
# --------------------------------------------------------------------------- #
def _usage_for(group: list[ExtractedSlide], archetype: str, slot_name: str) -> TextLimits:
    chars: list[int] = []
    lines: list[int] = []
    words: list[int] = []
    for slide in group:
        for mapped in _map_slide(slide, archetype):
            if mapped.name != slot_name or not _text_slot(archetype, mapped):
                continue
            text_shapes = [s for s in mapped.shapes if s.has_text()]
            if not text_shapes:
                continue
            chars.append(sum(len(s.text_joined()) for s in text_shapes))
            words.append(sum(s.word_count() for s in text_shapes))
            lines.append(max(len([p for p in s.text if p.text().strip()]) for s in text_shapes))

    def pct(values: list[int], q: float) -> int:
        if not values:
            return 0
        if len(values) < 5:
            return int(round(min(values))) if q < 0.5 else int(round(max(values)))
        return int(round(float(np.percentile(values, q))))

    min_chars = max(pct(chars, 5), 0)
    max_chars = min(max(pct(chars, 95), 20), 100_000)
    max_lines = max(min(pct(lines, 95), 40), 1)
    min_words = max(pct(words, 5), 0)
    max_words = max(pct(words, 95), 1)
    if max_chars < min_chars + 1:
        max_chars = min_chars + 20
    return TextLimits(
        min_chars=min_chars,
        max_chars=max_chars,
        max_lines=max_lines,
        min_words=min_words,
        max_words=max_words,
    )


def _words_total(group: list[ExtractedSlide]) -> tuple[int, int]:
    counts = sorted(total_words(s) for s in group)
    if not counts:
        return 0, 20
    if len(counts) < 5:
        median = counts[len(counts) // 2]
        maximum = counts[-1]
    else:
        median = float(np.median(counts))
        maximum = float(np.percentile(counts, 95))
    min_words = max(int(round(median * 0.3)), 0)
    max_words = max(int(round(maximum)), 20)
    return min_words, max_words


# --------------------------------------------------------------------------- #
# Portrait alternate arrangement
# --------------------------------------------------------------------------- #
def _portrait_alternate(slots: list[SlotDef]) -> AlternateArrangement | None:
    """Stack side-by-side columns vertically. Only emitted when a real
    columnar layout exists; secondary narrow slots are dropped from the alt."""
    column_slots = [s for s in slots if s.region.w < _HEADER_WIDTH]
    if len(column_slots) < 2:
        return None

    groups: list[list[SlotDef]] = []
    for slot in sorted(column_slots, key=lambda s: s.region.x):
        for group in groups:
            if any(_ranges_overlap(slot.region, g.region) for g in group):
                group.append(slot)
                break
        else:
            groups.append([slot])
    if len(groups) < 2:
        return None

    new_slots: list[SlotDef] = []
    for slot in slots:
        if slot.region.w >= _HEADER_WIDTH:
            new_slots.append(slot.model_copy(deep=True))

    col_start = min(s.region.y for s in column_slots)
    for group in sorted(groups, key=lambda g: min(s.region.x for s in g)):
        min_y = min(s.region.y for s in group)
        col_height = max(s.region.y + s.region.h for s in group) - min_y
        for slot in sorted(group, key=lambda s: s.region.y):
            rel = slot.region.y - min_y
            region = _clamp_region(
                0.5 - slot.region.w / 2, col_start + rel, slot.region.w, slot.region.h
            )
            copy = slot.model_copy(deep=True)
            copy.region = region
            new_slots.append(copy)
        col_start += col_height + _PORTRAIT_GUTTER

    if any(s.region.y + s.region.h > 1.0 + 1e-6 for s in new_slots):
        return None
    return AlternateArrangement(
        aspect_ratio="portrait",
        description="columns stacked vertically for tall slides",
        slots=new_slots,
    )


def _ranges_overlap(a: SlotRegion, b: SlotRegion) -> bool:
    return max(a.x, b.x) < min(a.x + a.w, b.x + b.w) - 0.002


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def _representative(group: list[ExtractedSlide]) -> ExtractedSlide:
    vectors = np.vstack([slide_features(s) for s in group])
    centroid = vectors.mean(axis=0)
    distances = np.linalg.norm(vectors - centroid, axis=1)
    return group[int(np.argmin(distances))]


def _blueprint_for(archetype: str, group: list[ExtractedSlide], _margin: Margins) -> Blueprint:
    rep = _representative(group)
    mapped = _map_slide(rep, archetype)
    named: dict[str, _MappedSlot] = {}
    read_order: list[str] = []

    def read_index(slot: _MappedSlot) -> int:
        return min(
            (rep.shapes.index(s) for s in slot.shapes if s in rep.shapes),
            default=len(rep.shapes) + 10,  # non-shape slots (charts) go last
        )

    for m in sorted(mapped, key=read_index):
        if m.name in named:
            named[m.name].shapes.extend(m.shapes)
            continue
        named[m.name] = m
        read_order.append(m.name)

    slots: list[SlotDef] = []
    for name in read_order:
        m = named[name]
        region = _region_for(m)
        if region is None:
            continue
        slot = _make_slot(archetype, m, region)
        if _text_slot(archetype, m):
            slot.text_limits = _usage_for(group, archetype, m.name)
        slots.append(slot)

    if not slots:
        fallback = _MappedSlot(
            "body",
            content_shapes(rep) or rep.shapes,
            kinds=[ContentKind.TEXT, ContentKind.PARAGRAPHS],
            style="body",
        )
        slots.append(_make_slot(archetype, fallback, _merged_region(fallback.shapes)))

    alternatives: list[AlternateArrangement] = []
    portrait = _portrait_alternate(slots)
    if portrait is not None:
        alternatives.append(portrait)

    min_words, max_words = _words_total(group)
    label = ARCHETYPE_LABELS.get(archetype, archetype.replace("-", " ").title())
    return Blueprint(
        id=archetype,
        archetype=Archetype(archetype),
        label=label,
        description=f"Derived statistically from {len(group)} representative slides in canon {archetype}",
        slots=slots,
        default_order=read_order,
        alternatives=alternatives,
        min_words_total=min_words,
        max_words_total=max_words,
        example_ref=None,
        example_thumbnail=None,
    )


def blueprints_from_slides(
    slides_by_archetype: dict[str, list[ExtractedSlide]], margin: Margins | None = None
) -> BlueprintLibrary:
    """Build a :class:`BlueprintLibrary`, one blueprint per archetype present.

    Only archetypes with a canonical slot vocabulary get blueprints in v1;
    discovered-but-unknown archetypes are merely recorded by the caller (see
    :mod:`cluster`). ``margin`` is accepted for API symmetry with the pack
    builder; geometry always comes from the real slide shapes.
    """
    library = BlueprintLibrary.empty()
    for archetype in sorted(slides_by_archetype):
        group = slides_by_archetype[archetype]
        if not group:
            continue
        if not (has_vocabulary(archetype) and archetype in _MAPPERS):
            continue
        library.add(_blueprint_for(archetype, group, margin or Margins()))
    # Validate: every entry must resolve for the canonical landscape ratio.
    for archetype in library.archetypes():
        library.resolve(archetype, "16:9")
    return library

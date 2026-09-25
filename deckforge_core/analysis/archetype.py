"""Structural heuristic archetype detection (Workstream B).

Deterministic, fast, pure rules — no vision model in v1 (the vision pass is
deferred per spec as optional). The same classifier is used by the pack builder
and, later, by QA.

Priority order
--------------
1. ``full-bleed-image``    one picture covering ~all of the slide (>= 85% of
                           both dimensions, within 5% of the slide bounds)
2. ``big-number``          a run >= 32pt whose text is numeric-only or "%"-text
3. ``title``               <= 3 text shapes, exactly one big text >= 30pt, all
                           other shapes <= 18pt with <= 12 words each (kicker/
                           subtitle scale), no body paragraphs, no charts/tables
4. ``section-divider``     one large text >= 24pt, all other shapes <= 18pt,
                           few words, no lists, no charts/tables
5. ``quote``               a shape whose text starts/ends with a quote mark,
                           few words
6. ``chart``               any chart on the slide
7. ``table``               any table on the slide
8. ``statement``           <= 4 text shapes, <= 25 words total, one shape
                           >= 22pt, none of the above
9. layout group (in internal order): ``closing`` (keyword + tiny text),
   ``image-left`` / ``image-right``, ``three-cards`` (3 equal row boxes),
   ``comparison`` (2 equal columns with headings), ``team`` (row of
   portrait cards: >= 2 side-by-side columns whose leading box is a photo),
   ``two-column-text`` (2 equal columns), ``agenda`` (short list + heading),
   ``timeline`` (connectors + >= 3 row boxes), ``process-flow`` (connectors +
   boxes)
10. fallback ``two-column-text`` (anything unrecognised)

Known heuristic ambiguity (documented, accept it in v1): a lone large-sentence
slide and a big "Thank you" without other markers classify as ``title``;
single-shape slides that hit none of the structural rules fall to the
``two-column-text`` fallback.

All geometry is in RELATIVE (0..1) units per the ingest contract.
"""

from __future__ import annotations

from deckforge_core.analysis.features import _shape_max_pt, largest_run_pt
from deckforge_core.schemas.extracted import ExtractedSlide

_NUMERIC_EXTRA = set("0123456789.,%$#-+x\u00d7() ")
_QUOTE_CHARS = set("\u201c\u201d\"'\u00ab\u00bb\u201e\u2018\u2019")
_CLOSING_KEYWORDS = (
    "thank",
    "thanks",
    "contact",
    "questions",
    "next steps",
    "get in touch",
    "let's talk",
)

_LOOKS_LIKE_HEADER_THRESHOLD = 0.65  # shapes wider than this are full-width headers


def is_numeric_text(text: str) -> bool:
    """True when ``text`` is a number-like token: digits plus only
    ``.,%$#-+x*()``/space characters and at least one digit."""
    t = text.strip()
    return bool(t) and any(c.isdigit() for c in t) and all(c in _NUMERIC_EXTRA for c in t)


def has_quote_marks(text: str) -> bool:
    t = text.strip()
    return len(t) >= 1 and (t[0] in _QUOTE_CHARS or t[-1] in _QUOTE_CHARS)


def content_shapes(slide: ExtractedSlide):
    """Meaningful shapes (text or image), excluding degenerately small or
    full-bleed-background shapes. Header-width shapes are kept; column grouping
    separates them later."""
    out = []
    for s in slide.shapes:
        if not (s.has_text() or s.image is not None):
            continue
        if s.w < 0.05 and s.h < 0.02:
            continue
        if s.w >= 0.98 and s.h >= 0.98:
            continue
        out.append(s)
    return out


def _x_overlaps(a, b, eps: float = 0.002) -> bool:
    return max(a.x, b.x) < min(a.x + a.w, b.x + b.w) - eps


def columns(slide: ExtractedSlide):
    """Group content shapes into side-by-side columns.

    Shapes in the same column share overlapping x-ranges; two mounted boxes of
    a two-column layout fall into separate columns because their x-ranges are
    disjoint. Full-width header shapes (``w >= 0.65``) are excluded so a title
    spanning the whole slide does not glue the columns together.
    """
    shapes = [s for s in content_shapes(slide) if s.w < _LOOKS_LIKE_HEADER_THRESHOLD]
    shapes.sort(key=lambda s: s.x)
    groups: list[list] = []
    for shape in shapes:
        for group in groups:
            if any(_x_overlaps(shape, member) for member in group):
                group.append(shape)
                break
        else:
            groups.append([shape])
    for group in groups:
        group.sort(key=lambda s: s.y)
    return groups


def _in_row_band(shapes, tol: float = 0.12) -> bool:
    if not shapes:
        return False
    ys = [s.y for s in shapes]
    bottoms = [s.y + s.h for s in shapes]
    return max(ys) - min(ys) < tol and max(bottoms) - min(bottoms) < tol


def _similar_extent(shapes, attr: str, tol: float = 0.12) -> bool:
    values = [getattr(s, attr) for s in shapes]
    if len(values) < 2:
        return True
    avg = sum(values) / len(values)
    if avg <= 0:
        return all(v <= 0.01 for v in values)
    return all(abs(v - avg) / avg <= tol for v in values)


def _evenly_spaced(shapes, tol: float = 0.06) -> bool:
    if len(shapes) < 3:
        return True
    order = sorted(shapes, key=lambda s: s.x)
    gaps = [order[i + 1].x - (order[i].x + order[i].w) for i in range(len(order) - 1)]
    avg = sum(gaps) / len(gaps)
    if avg <= 0:
        return False
    return all(abs(g - avg) <= tol for g in gaps)


def _picture_shapes(slide):
    return [s for s in slide.shapes if s.image is not None]


def _has_substantial_picture(slide) -> bool:
    """A real photo/illustration (>= 20% x 25% of the slide) disqualifies the
    pure-text archetypes (title/section-divider/statement/...)."""
    return any(p.w >= 0.2 and p.h >= 0.25 for p in _picture_shapes(slide))


# --------------------------------------------------------------------------- #
# Individual rules. Each returns (archetype, confidence) or None.
# --------------------------------------------------------------------------- #
def _rule_full_bleed(slide: ExtractedSlide):
    if slide.has_image_slides_whole_thing:
        return "full-bleed-image", 0.95
    for p in _picture_shapes(slide):
        if (
            p.w >= 0.85
            and p.h >= 0.85
            and p.x <= 0.05
            and p.y <= 0.05
            and p.x + p.w >= 0.95
            and p.y + p.h >= 0.95
        ):
            return "full-bleed-image", 0.95
    return None


def _rule_big_number(slide: ExtractedSlide):
    for shape in slide.shapes:
        for para in shape.text:
            for run in para.runs:
                if run.size_pt and run.size_pt >= 32 and is_numeric_text(run.text):
                    return "big-number", 0.92
    return None


def _text_shapes(slide):
    return [s for s in slide.shapes if s.has_text()]


def _rule_title(slide: ExtractedSlide):
    if slide.charts or slide.tables or _has_substantial_picture(slide):
        return None
    shapes = _text_shapes(slide)
    if not 1 <= len(shapes) <= 3:
        return None
    big = [s for s in shapes if _shape_max_pt(s) >= 30.0]
    small = [s for s in shapes if 0 < _shape_max_pt(s) <= 18.0]
    if len(big) != 1 or len(small) != len(shapes) - 1:
        return None
    if sum(s.word_count() for s in shapes) > 60:
        return None
    if any(len([p for p in s.text if p.text().strip()]) >= 3 for s in small):
        return None
    if any(s.word_count() > 12 for s in small):
        return None
    return "title", 0.85


def _rule_section_divider(slide: ExtractedSlide):
    if slide.charts or slide.tables or _has_substantial_picture(slide):
        return None
    shapes = _text_shapes(slide)
    if not 2 <= len(shapes) <= 3:
        return None
    if any(has_quote_marks(s.text_joined()) for s in shapes):
        return None
    big = [s for s in shapes if _shape_max_pt(s) >= 24.0]
    small = [s for s in shapes if 0 < _shape_max_pt(s) <= 18.0]
    if len(big) != 1 or len(small) != len(shapes) - 1:
        return None
    if sum(s.word_count() for s in shapes) > 50:
        return None
    if any(len([p for p in s.text if p.text().strip()]) >= 3 for s in shapes):
        return None
    return "section-divider", 0.78


def _rule_quote(slide: ExtractedSlide):
    if slide.charts or slide.tables:
        return None
    shapes = [s for s in content_shapes(slide) if s.has_text()]
    if not shapes or len(shapes) > 3:
        return None
    if sum(s.word_count() for s in shapes) > 70:
        return None
    quoted = [s for s in shapes if has_quote_marks(s.text_joined())]
    if quoted:
        return "quote", 0.85
    return None


def _rule_chart(slide: ExtractedSlide):
    if slide.charts:
        return "chart", 0.92
    return None


def _rule_table(slide: ExtractedSlide):
    if slide.tables:
        return "table", 0.92
    return None


def _rule_statement(slide: ExtractedSlide):
    if slide.charts or slide.tables or _has_substantial_picture(slide):
        return None
    shapes = _text_shapes(slide)
    if not shapes or len(shapes) > 4:
        return None
    if sum(s.word_count() for s in shapes) > 25:
        return None
    if largest_run_pt(slide) < 22.0:
        return None
    return "statement", 0.65


def _rule_closing(slide: ExtractedSlide):
    if slide.charts or slide.tables or _has_substantial_picture(slide):
        return None
    shapes = _text_shapes(slide)
    if not 1 <= len(shapes) <= 3:
        return None
    lower = " ".join(s.text_joined() for s in shapes).lower()
    words = sum(s.word_count() for s in shapes)
    if words > 25:
        return None
    if any(kw in lower for kw in _CLOSING_KEYWORDS):
        return "closing", 0.6
    return None


def _rule_image_side(slide: ExtractedSlide):
    for p in _picture_shapes(slide):
        if p.w < 0.18 or p.h < 0.22:
            continue
        if p.x + p.w <= 0.55:
            return "image-left", 0.85
        if p.x >= 0.45:
            return "image-right", 0.85
    return None


def _rule_three_cards(slide: ExtractedSlide):
    cols = columns(slide)
    if len(cols) != 3:
        return None
    boxes = [c[0] for c in cols]
    # one box per column, sitting together in a single identical row
    if not all(len(c) == 1 for c in cols):
        return None
    if not (_in_row_band(boxes) and _similar_extent(boxes, "w") and _similar_extent(boxes, "h")):
        return None
    if not _evenly_spaced(boxes):
        return None
    if any(len([p for p in b.text if p.text().strip()]) > 2 for b in boxes):
        return None
    return "three-cards", 0.85


def _column_has_heading(col) -> bool:
    if not col:
        return False
    top = col[0]
    paras = [p for p in top.text if p.text().strip()]
    if not paras:
        return False
    words = paras[0].word_count()
    if words == 0:
        return False
    short_lead = words <= 10
    multiple_lines = len(paras) >= 2 or len(col) >= 2
    with_size = _shape_max_pt(top) >= 15.0
    return short_lead and (multiple_lines or with_size)


def _rule_comparison(slide: ExtractedSlide):
    cols = columns(slide)
    if len(cols) != 2:
        return None
    if not _similar_extent([c[0] for c in cols], "w"):
        return None
    if _column_has_heading(cols[0]) and _column_has_heading(cols[1]):
        return "comparison", 0.78
    return None


def _rule_two_column(slide: ExtractedSlide):
    cols = columns(slide)
    if len(cols) < 2:
        return None
    if not _similar_extent([c[0] for c in cols], "w"):
        return None
    return "two-column-text", 0.68


def _rule_agenda(slide: ExtractedSlide):
    if slide.charts or slide.tables:
        return None
    shapes = content_shapes(slide)
    if len(shapes) < 2:
        return None
    list_shape = None
    for s in shapes:
        paras = [p for p in s.text if p.text().strip()]
        if len(paras) >= 3:
            lines = [p.text().strip() for p in paras]
            if all(len(line) <= 80 for line in lines):
                list_shape = s
                break
    if list_shape is None:
        return None
    if largest_run_pt(slide) < 18.0:
        return None
    return "agenda", 0.6


def _rule_timeline(slide: ExtractedSlide):
    if not slide.connectors:
        return None
    boxes = [s for s in content_shapes(slide) if s.w >= 0.08 and s.h >= 0.03]
    if len(boxes) < 3:
        return None
    bands: list[list] = []
    for b in boxes:
        merged = None
        for band in bands:
            rep = band[0]
            overlap = max(b.y, rep.y) < min(b.y + b.h, rep.y + rep.h)
            if overlap and abs(b.y - rep.y) < 0.15:
                merged = band
                break
        if merged is None:
            bands.append([b])
        else:
            merged.append(b)
    row = max(bands, key=len)
    if len(row) < 3:
        return None
    if not (_in_row_band(row) and _similar_extent(row, "w") and _evenly_spaced(row)):
        return None
    return "timeline", 0.7


def _rule_process_flow(slide: ExtractedSlide):
    if not slide.connectors:
        return None
    boxes = [s for s in content_shapes(slide) if s.w >= 0.08 and s.h >= 0.03]
    if len(boxes) >= 2:
        return "process-flow", 0.6
    return None


def _rule_team(slide: ExtractedSlide):
    cols = columns(slide)
    if len(cols) < 2:
        return None
    cards = [c[0] for c in cols]
    if not (_in_row_band(cards) and _similar_extent(cards, "w")):
        return None
    # A team card is recognisable by its portrait; pure text columns should
    # stay two-column-text / comparison even when equally sized.
    with_portrait = sum(1 for c in cards if c.image is not None)
    if len(cards) >= 2 and with_portrait >= len(cards) - 1:
        return "team", 0.7
    return None


# Ordered rule list — the documented priority order. New rules are added here.
_RULES: tuple = (
    _rule_full_bleed,
    _rule_big_number,
    _rule_title,
    _rule_section_divider,
    _rule_quote,
    _rule_chart,
    _rule_table,
    _rule_agenda,
    _rule_statement,
    _rule_closing,
    _rule_image_side,
    _rule_three_cards,
    _rule_comparison,
    _rule_team,
    _rule_timeline,
    _rule_two_column,
    _rule_process_flow,
)


def detect_archetype(slide: ExtractedSlide) -> tuple[str, float]:
    """Return ``(canonical_archetype, confidence)`` for ``slide``.

    Rules run in the priority order documented at the top of this module; the
    first match wins. The fallback ``two-column-text`` (confidence 0.2) is
    returned when nothing matches.
    """
    for rule in _RULES:
        hit = rule(slide)
        if hit is not None:
            return hit
    return "two-column-text", 0.2

"""`compose`: fill a user-supplied template with per-slide content.

Workflow: extract the template's real layout/style on the fly, then render the
user's content into it. No corpus or learned pack required — the template's own
slides define the palette, typography, grid and blueprints, and ``normalise_plan``
bridges the content to the template's actual slots.

This is the "give me a template + content per slide" path: ``deckforge compose``
turns a plain .pptx template plus a JSON content file into a polished, native,
editable deck in the template's visual language.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from deckforge_core.analysis.archetype import detect_archetype
from deckforge_core.analysis.blueprint import blueprints_from_slides
from deckforge_core.analysis.style_profile import style_from_decks
from deckforge_core.ingest.parser import extract_deck
from deckforge_core.modes.common import ModeError, normalise_plan, pptx_path
from deckforge_core.renderer import render_deck
from deckforge_core.schemas.archetypes import ARCHETYPE_ORDER
from deckforge_core.schemas.deck_plan import DeckPlan, ImageReq, SlidePlan, SlotValue
from deckforge_core.schemas.pack import FormatPack

PREFERRED_FALLBACK = "two-column-text"


@dataclass
class ComposeResult:
    out_path: str
    slide_count: int
    notes: list[str] = field(default_factory=list)


# Content key -> canonical blueprint slot name.
_ALIASES = {
    "kicker": "kicker",
    "subtitle": "subtitle",
    "statement": "statement",
    "transition": "statement",
    "body": "body",
    "bullets": "body",
    "points": "body",
    "col_a": "col_a_body",
    "col_left": "col_a_body",
    "left": "col_a_body",
    "a": "col_a_body",
    "col_b": "col_b_body",
    "col_right": "col_b_body",
    "right": "col_b_body",
    "b": "col_b_body",
    "card_1": "card_1",
    "card_2": "card_2",
    "card_3": "card_3",
    "source": "source",
    "contact": "contact",
    "caption": "caption",
}

_PARAGRAPH_SLOTS = {"body", "col_a_body", "col_b_body", "card_1", "card_2", "card_3"}
_TEXT_SLOTS = {"kicker", "subtitle", "statement", "contact", "caption", "source"}


def _paragraphs(content) -> list[str]:
    if isinstance(content, str):
        return [p for p in content.splitlines() if p.strip()]
    return [str(p) for p in content]


def _image_req(content) -> ImageReq:
    if isinstance(content, dict):
        return ImageReq(
            query=content.get("query"),
            url=content.get("url"),
            alt=content.get("alt"),
        )
    text = str(content)
    if text.lower().startswith(("http://", "https://")) or Path(text).suffix.lower() in (
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
    ):
        return ImageReq(url=text)
    return ImageReq(query=text)


def _load_content(path: Path) -> list[dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ModeError(f"cannot read content JSON {path}: {exc}") from exc
    if isinstance(raw, list):
        slides = raw
    elif isinstance(raw, dict) and isinstance(raw.get("slides"), list):
        slides = raw["slides"]
    else:
        raise ModeError(
            "content file must be a JSON array of slide objects, or "
            '{"title": ..., "slides": [...]}'
        )
    if not slides:
        raise ModeError("content file has no slides")
    return slides


def _slots_from_spec(spec: dict) -> dict[str, SlotValue]:
    """Map user-friendly content keys onto blueprint slot values."""
    slots: dict[str, SlotValue] = {}
    for key, canonical in _ALIASES.items():
        if key not in spec:
            continue
        content = spec[key]
        if canonical in _PARAGRAPH_SLOTS:
            slots[canonical] = SlotValue(paragraphs=_paragraphs(content))
        elif canonical in _TEXT_SLOTS:
            slots[canonical] = SlotValue(text=str(content))
    if "image" in spec:
        slots["image"] = SlotValue(image=_image_req(spec["image"]))
    return slots


def _pick_archetype(
    provided_slots: set[str],
    template_archetype: str,
    library_archetypes: set[str],
    blueprint_slots: dict[str, set[str]],
) -> str:
    """Choose the blueprint that best fits the provided content.

    Prefers an archetype whose blueprint can actually hold the content; the
    template's own archetype wins ties so the output still reads like the
    template. ``forced`` archetypes override this entirely.
    """
    best: Optional[str] = None
    best_score = -1.0
    for archetype in library_archetypes:
        overlap = len(provided_slots & blueprint_slots.get(archetype, set()))
        bias = 0.5 if archetype == template_archetype else 0.0
        score = overlap + bias
        if score > best_score:
            best, best_score = archetype, score
    if best is None or best_score <= 0.0:
        if template_archetype in library_archetypes:
            return template_archetype
        if PREFERRED_FALLBACK in library_archetypes:
            return PREFERRED_FALLBACK
        return next(iter(library_archetypes))
    return best


def _blueprint_slots_for(library) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for archetype in library.archetypes():
        blueprint = library.get(archetype)
        out[archetype] = {slot.name for slot in blueprint.slots} if blueprint else set()
    return out


def run_compose(
    template: str,
    content_file: str,
    out_path: str,
    *,
    aspect: Optional[str] = None,
    warnings: Optional[list[str]] = None,
) -> ComposeResult:
    """Render ``content_file``'s per-slide content into ``template``'s format."""
    sink = warnings if warnings is not None else []
    template_path = Path(template).expanduser()
    if not template_path.is_file():
        raise ModeError(f"template not found: {template_path}")

    deck = extract_deck(template_path)
    if not deck.slides:
        raise ModeError(f"template has no slides: {template_path}")

    content = _load_content(Path(content_file).expanduser())
    if len(content) > len(deck.slides):
        sink.append(
            f"template has {len(deck.slides)} slides; slides {len(deck.slides) + 1}-"
            f"{len(content)} recycle the last layout."
        )

    style = style_from_decks([deck])
    grouped: dict[str, list] = {}
    template_archetypes: list[str] = []
    for slide in deck.slides:
        archetype, _ = detect_archetype(slide)
        grouped.setdefault(archetype, []).append(slide)
        if archetype not in template_archetypes:
            template_archetypes.append(archetype)
    library = blueprints_from_slides(grouped)
    known = library.archetypes()
    blueprint_slots = _blueprint_slots_for(library)
    known_set = set(known)

    pack_aspect = aspect or deck.aspect_ratio
    pack = FormatPack(
        name=template_path.stem,
        source_deck_count=1,
        source_slide_count=len(deck.slides),
        aspect_ratios=[pack_aspect],
        archetypes=list(known) if known else template_archetypes,
        style=style,
    )

    plan_slides: list[SlidePlan] = []
    for index, spec in enumerate(content, start=1):
        template_index = min(index - 1, len(template_archetypes) - 1)
        template_archetype = template_archetypes[template_index]
        slots_map = _slots_from_spec(spec)
        forced = spec.get("archetype")
        if forced and forced not in ARCHETYPE_ORDER:
            raise ModeError(
                f"unknown archetype {forced!r}; use one of: {', '.join(ARCHETYPE_ORDER)}"
            )
        archetype = (
            forced
            if forced and forced in known_set
            else _pick_archetype(set(slots_map), template_archetype, known_set, blueprint_slots)
        )
        if forced and forced not in known_set:
            sink.append(
                f"slide {index}: forced archetype {forced!r} is not in the template's "
                f"layouts; using {archetype!r} instead"
            )
        title = spec.get("title", "").strip() or None
        plan_slides.append(
            SlidePlan(
                n=index,
                archetype=archetype,
                title=title,
                slots=slots_map,
                speaker_notes=spec.get("notes"),
                section=spec.get("section"),
            )
        )

    plan = DeckPlan(
        title=plan_slides[0].title or template_path.stem,
        aspect_ratio=pack_aspect,
        pack=pack.name,
        created_by="compose",
        slides=plan_slides,
    )
    sink.extend(normalise_plan(plan, library))

    result = render_deck(plan, pack, library, pptx_path(out_path), warnings=sink)
    return ComposeResult(
        out_path=str(result.out_path),
        slide_count=result.slide_count,
        notes=list(sink),
    )

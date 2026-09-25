"""Shared helpers for Phase 2 mode commands (`learn`, `make`, ...)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from deckforge_core.analysis.features import title_shape
from deckforge_core.config import ensure_dirs
from deckforge_core.errors import DeckForgeError
from deckforge_core.renderer.pack_io import load_pack, save_pack
from deckforge_core.schemas.blueprints import BlueprintLibrary
from deckforge_core.schemas.deck_plan import DeckPlan, SlidePlan, SlotValue
from deckforge_core.schemas.extracted import ExtractedSlide
from deckforge_core.schemas.pack import FormatPack


class ModeError(DeckForgeError):
    """A mode command failed (bad input, missing pack, ...)."""


def packs_root() -> "Path":
    """The directory where learned packs are stored."""
    return ensure_dirs()["packs"]


def pack_dir_for(name: str) -> "Path":
    return packs_root() / name


def pptx_path(out_path: str | Path) -> Path:
    """Normalise an output path so it always carries the ``.pptx`` suffix."""
    path = Path(out_path).expanduser()
    if not path.suffix:
        return path.with_name(path.name + ".pptx")
    return path


def resolve_pack(spec: str) -> Tuple[FormatPack, BlueprintLibrary]:
    """Load (pack, blueprints) from a pack ``spec``.

    ``spec`` is either a pack NAME under the data directory's packs folder, a
    directory path containing a saved pack, or a ``.dfpack`` archive path.
    """
    candidate = Path(spec).expanduser()
    if candidate.is_file() and candidate.suffix.lower() == ".dfpack":

        dest = pack_dir_for(candidate.stem)
        return load_pack(dest) if dest.exists() else _import_dfpack(candidate, dest)

    if candidate.is_dir() and (candidate / "pack.json").is_file():
        return load_pack(candidate)

    named = pack_dir_for(spec)
    if named.is_dir() and (named / "pack.json").is_file():
        return load_pack(named)

    if (named / "pack.json").is_file() is False and candidate.exists():
        raise ModeError(f"folder {candidate} does not contain a saved pack (no pack.json)")

    available = list_packs()
    raise ModeError(
        f"pack {spec!r} not found. Available packs: "
        + (", ".join(available) if available else "none (run `deckforge learn`)")
    )


def _import_dfpack(zip_path: "Path", dest: "Path") -> Tuple[FormatPack, BlueprintLibrary]:
    from deckforge_core.renderer.pack_io import load_dfpack

    return load_dfpack(zip_path, dest)


def list_packs() -> "list[str]":
    from deckforge_core.renderer.pack_io import list_packs as _list

    return _list(packs_root())


def save_new_pack(name: str, pack: FormatPack, blueprints: BlueprintLibrary) -> "Path":
    """Persist ``pack`` under the data directory and return its directory."""
    target = pack_dir_for(name)
    save_pack(pack, blueprints, target)
    return target


def plan_from_deck(
    slides: "list[ExtractedSlide]",
    pack: FormatPack,
    library: Optional["BlueprintLibrary"] = None,
) -> DeckPlan:
    """Build a plan whose slide shapes mirror an extracted deck (restyle base).

    Each slide gets its detected archetype and, where the blueprint exposes a
    ``title`` slot, the slide's most prominent heading text. No styling or
    layout knowledge leaks in here — the renderer derives everything from the
    pack.
    """
    from deckforge_core.analysis.archetype import detect_archetype

    aspect = "16:9"
    if slides and getattr(slides[0], "aspect_ratio", None):
        aspect = slides[0].aspect_ratio
    plan_slides: list[SlidePlan] = []
    for index, slide in enumerate(slides, start=1):
        archetype, _ = detect_archetype(slide)
        slots: dict[str, SlotValue] = {}
        if library is not None:
            blueprint = library.get(archetype)
            known = {slot.name for slot in blueprint.slots} if blueprint else set()
        else:
            known = set()
        if "title" in known:
            heading = _slide_heading(slide)
            if heading:
                slots["title"] = SlotValue(text=heading)
        plan_slides.append(
            SlidePlan(
                n=index,
                archetype=archetype,
                title=_slide_heading(slide),
                slots=slots,
                speaker_notes=slide.notes_text or None,
            )
        )
    return DeckPlan(
        title=plan_slides[0].title or "Restyled deck" if plan_slides else "Deck",
        aspect_ratio=aspect,
        pack=pack.name,
        created_by="plan-from-deck",
        slides=plan_slides,
    )


def _slide_heading(slide: ExtractedSlide) -> Optional[str]:
    shape = title_shape(slide)
    if shape is None:
        return None
    text = shape.text_joined().strip()
    if not text:
        return None
    return text[:200]


@dataclass
class LearnSummary:
    pack: FormatPack
    pack_dir: "Path"
    decks: int
    slides: int


def summarize_pack(pack: FormatPack, pack_dir: "Path") -> LearnSummary:
    return LearnSummary(
        pack=pack,
        pack_dir=pack_dir,
        decks=pack.source_deck_count,
        slides=pack.source_slide_count,
    )


def normalise_plan(plan: DeckPlan, library: BlueprintLibrary) -> list[str]:
    """Align a planned deck with the pack's actual blueprint slots.

    The planner/AI fills the canonical vocabulary; learned blueprints sometimes
    expose fewer regions (e.g. two-column blueprints fold the column heading
    into the body). Content must never be dropped silently, so:

    * ``*_heading`` text is prepended to the matching ``*_body`` paragraph list
      when no heading slot exists;
    * any other plan slot the blueprint does not expose is removed, and a note
      is returned so the CLI can mention it.

    Returns a list of human-readable notes about adjusted slides.
    """
    notes: list[str] = []
    for slide in plan.slides:
        blueprint = library.get(slide.archetype)
        if blueprint is None:
            continue
        known = {slot.name for slot in blueprint.slots}
        for side in ("col_a", "col_b", "left", "right"):
            heading = f"{side}_heading"
            if heading in slide.slots and heading not in known:
                body_name = f"{side}_body"
                heading_value = slide.slots.pop(heading)
                if body_name in known:
                    body = slide.slots.setdefault(body_name, SlotValue())
                    if body.paragraphs is None:
                        body.paragraphs = []
                    if heading_value.text:
                        body.paragraphs.insert(0, heading_value.text)
                    elif heading_value.paragraphs:
                        body.paragraphs[0:0] = heading_value.paragraphs
                    notes.append(
                        f"slide {slide.n}: merged {heading} into {body_name} "
                        f"(pack blueprint has no {heading} slot)"
                    )
        for name in list(slide.slots):
            if name not in known:
                slide.slots.pop(name, None)
                notes.append(
                    f"slide {slide.n}: dropped {name!r} (blueprint "
                    f"{slide.archetype!r} has no such slot)"
                )
    return notes

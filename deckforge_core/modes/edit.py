"""`edit`: load a saved DeckPlan JSON, apply slot edits, re-render."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from deckforge_core.modes.common import ModeError, normalise_plan, pptx_path, resolve_pack
from deckforge_core.renderer.engine import RenderResult, render_deck
from deckforge_core.schemas.deck_plan import DeckPlan, SlotValue


@dataclass
class EditSpec:
    slide: int
    slot: str
    field: str
    value: str


def parse_edit(spec: str) -> EditSpec:
    if "=" not in spec:
        raise ModeError(f"edit must look like SLIDE:SLOT[.FIELD]=VALUE, got {spec!r}")
    key, raw_value = spec.split("=", 1)
    key, value = key.strip(), raw_value.strip()
    if ":" not in key:
        raise ModeError(f"edit key {key!r} has no SLIDE:SLOT separator")
    slide_text, slot_part = key.split(":", 1)
    try:
        slide_n = int(slide_text)
    except ValueError:
        raise ModeError(f"slide number {slide_text!r} is not an integer")
    if "." in slot_part:
        slot, field = slot_part.rsplit(".", 1)
    else:
        slot, field = slot_part, "text"
    if not slot or not value:
        raise ModeError(f"edit {spec!r} needs a slot name and a value")
    return EditSpec(slide=slide_n, slot=slot, field=field, value=value)


def apply_edits(plan: DeckPlan, edits: list[EditSpec]) -> int:
    applied = 0
    for edit in edits:
        slide = next((s for s in plan.slides if s.n == edit.slide), None)
        if slide is None:
            raise ModeError(
                f"edit references slide {edit.slide} but plan has "
                f"{len(plan.slides)} slides"
            )
        value = slide.slots.setdefault(edit.slot, SlotValue())
        if edit.field == "text":
            value.text = edit.value
        elif edit.field in ("paragraphs", "items"):
            setattr(value, edit.field, [p.strip() for p in edit.value.split("|") if p.strip()])
        elif edit.field == "number":
            value.number = _to_number(edit.value)
        elif edit.field == "source":
            value.source = edit.value
        elif edit.field == "remove":
            slide.slots.pop(edit.slot, None)
            continue
        else:
            raise ModeError(f"unknown slot field {edit.field!r} (text|paragraphs|items|number|source|remove)")
        applied += 1
    return applied


def _to_number(value: str):
    try:
        return float(value) if "." in value else int(value)
    except ValueError:
        return value


class EditResult:
    def __init__(self, plan: DeckPlan, render: RenderResult, applied: int) -> None:
        self.plan = plan
        self.render = render
        self.applied = applied


def run_edit(
    plan_json: Path,
    edits: list[str],
    out_path: Path,
    pack_spec: Optional[str] = None,
    *,
    warnings: Optional[list[str]] = None,
) -> EditResult:
    plan_json = Path(plan_json).expanduser()
    if not plan_json.is_file():
        raise ModeError(f"plan file not found: {plan_json}")
    parsed = [parse_edit(edit) for edit in edits]
    if not parsed:
        raise ModeError("no edits given (use -e SLIDE:SLOT.FIELD=VALUE)")

    plan = DeckPlan.model_validate_json(plan_json.read_text(encoding="utf-8"))
    pack, library = resolve_pack(pack_spec or plan.pack)
    applied = apply_edits(plan, parsed)

    sink = warnings if warnings is not None else []
    sink.extend(normalise_plan(plan, library))
    result = render_deck(plan, pack, library, pptx_path(out_path), warnings=sink)
    return EditResult(plan=plan, render=result, applied=applied)

"""`make`: plan + render a deck from a prompt and a Format Pack."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from deckforge_core.config import Settings
from deckforge_core.modes.common import ModeError, normalise_plan, pptx_path, resolve_pack
from deckforge_core.planner.planner import PlannerOptions, plan_deck
from deckforge_core.renderer import render_deck
from deckforge_core.schemas.deck_plan import DeckPlan


@dataclass
class MakeResult:
    plan: DeckPlan
    width: float
    height: float
    out_path: str
    slide_count: int


def run_make(
    prompt: str,
    pack_spec: str,
    out_path: str,
    *,
    slides: int = 10,
    tone: str = "professional",
    audience: str = "",
    aspect: str = "16:9",
    provider: Optional[str] = None,
    save_plan: Optional[str] = None,
    warnings: Optional[list[str]] = None,
) -> MakeResult:
    if not prompt or not prompt.strip():
        raise ModeError("a non-empty prompt/brief is required")
    if slides < 1:
        raise ModeError("--slides must be >= 1")

    pack, library = resolve_pack(pack_spec)
    options = PlannerOptions(
        slide_count=slides,
        tone=tone,
        audience=audience,
        aspect_ratio=aspect,
    )
    plan = plan_deck(
        prompt,
        pack,
        options=options,
        settings=Settings(),
        llm_provider=provider,
    )
    sink = warnings if warnings is not None else []
    sink.extend(normalise_plan(plan, library))

    result = render_deck(plan, pack, library, pptx_path(out_path), warnings=sink)

    if save_plan:
        Path(save_plan).write_text(plan.model_dump_json(indent=2), encoding="utf-8")

    from deckforge_core.renderer.canvas import canvas_size

    width, height = canvas_size(plan.aspect_ratio or aspect)
    return MakeResult(
        plan=plan,
        width=width,
        height=height,
        out_path=str(result.out_path),
        slide_count=result.slide_count,
    )

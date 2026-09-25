"""`outline`: show the structure a prompt would produce for a pack."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from deckforge_core.config import Settings
from deckforge_core.modes.common import resolve_pack
from deckforge_core.planner.planner import PlannerOptions, plan_deck


@dataclass
class OutlineLine:
    n: int
    archetype: str
    title: Optional[str]


def run_outline(
    prompt: str,
    pack_spec: str,
    *,
    slides: int = 10,
    tone: str = "professional",
    audience: str = "",
    aspect: str = "16:9",
    provider: Optional[str] = None,
) -> list[OutlineLine]:
    pack, _ = resolve_pack(pack_spec)
    options = PlannerOptions(
        slide_count=slides, tone=tone, audience=audience, aspect_ratio=aspect
    )
    plan = plan_deck(
        prompt, pack, options=options, settings=Settings(), llm_provider=provider
    )
    return [
        OutlineLine(n=s.n, archetype=s.archetype, title=s.title or "--")
        for s in plan.slides
    ]

"""`restyle`: re-render an existing deck through a chosen Format Pack."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from deckforge_core.ingest.parser import extract_deck
from deckforge_core.modes.common import ModeError, plan_from_deck, pptx_path, resolve_pack
from deckforge_core.renderer.engine import RenderResult, render_deck


def run_restyle(
    deck_path: Path,
    pack_spec: str,
    out_path: Path,
    *,
    warnings: Optional[list[str]] = None,
) -> RenderResult:
    deck_path = Path(deck_path).expanduser()
    if not deck_path.is_file():
        raise ModeError(f"deck not found: {deck_path}")
    pack, library = resolve_pack(pack_spec)

    deck = extract_deck(deck_path)
    if not deck.slides:
        raise ModeError(f"no slides extracted from {deck_path}")
    plan = plan_from_deck(deck.slides, pack, library)

    sink = warnings if warnings is not None else []
    return render_deck(plan, pack, library, pptx_path(out_path), warnings=sink)

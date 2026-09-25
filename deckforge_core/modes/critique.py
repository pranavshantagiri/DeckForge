"""`critique`: run QA checks on a deck through a Format Pack (offline by default)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from deckforge_core.ingest.parser import extract_deck
from deckforge_core.modes.common import ModeError, plan_from_deck, resolve_pack
from deckforge_core.qa.runner import run_qa
from deckforge_core.schemas.qa import QASummaryReport


def run_critique(
    deck_path: Path,
    pack_spec: str,
    *,
    out_dir: Path,
    render_backend: str = "none",
    provider: Optional[str] = None,
    aspect: str = "16:9",
) -> QASummaryReport:
    deck_path = Path(deck_path).expanduser()
    if not deck_path.is_file():
        raise ModeError(f"deck not found: {deck_path}")
    pack, library = resolve_pack(pack_spec)

    deck = extract_deck(deck_path)
    if not deck.slides:
        raise ModeError(f"no slides extracted from {deck_path}")
    plan = plan_from_deck(deck.slides, pack, library)

    report = run_qa(
        plan,
        pack,
        library,
        render_backend=render_backend,
        out_dir=out_dir,
        max_iters=1,
    )
    return report

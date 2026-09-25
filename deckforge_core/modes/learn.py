"""`learn`: build a Format Pack from a folder of .pptx decks."""

from __future__ import annotations

from pathlib import Path

from deckforge_core.analysis.build_pack import learn_pack as _learn_pack_core
from deckforge_core.modes.common import (
    LearnSummary,
    ModeError,
    pack_dir_for,
    summarize_pack,
)


def discover_decks(folder: Path) -> list[Path]:
    return sorted(folder.rglob("*.pptx"))


def run_learn(
    source: Path,
    name: str,
    *,
    use_cache: bool = True,
    max_decks: int = 0,
) -> LearnSummary:
    source = Path(source).expanduser()
    if not source.is_dir():
        raise ModeError(f"source is not a directory: {source}")

    decks = discover_decks(source)
    if not decks:
        raise ModeError(f"no .pptx decks found in {source}")
    if max_decks > 0:
        decks = decks[:max_decks]

    pack = _learn_pack_core(
        source,
        name,
        target_dir=pack_dir_for(name),
        use_cache=use_cache,
        max_decks=max_decks,
    )
    target = pack_dir_for(name)
    return summarize_pack(pack, target)

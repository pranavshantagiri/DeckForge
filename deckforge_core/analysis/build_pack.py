"""Learn a Format Pack from a folder of .pptx decks (Workstream B).

Orchestrates ingestion → clustering → archetype detection → style derivation →
blueprint building, then persists the pack through Workstream C's
:func:`deckforge_core.renderer.pack_io.save_pack`.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from deckforge_core.analysis.archetype import detect_archetype
from deckforge_core.analysis.blueprint import blueprints_from_slides
from deckforge_core.analysis.cluster import (
    DiscoveredCluster,
    cluster_slides,
    discover_archetypes,
    embed_slides,
)
from deckforge_core.analysis.style_profile import style_from_decks
from deckforge_core.ingest.parser import extract_directory
from deckforge_core.renderer.pack_io import save_pack
from deckforge_core.schemas.archetypes import ARCHETYPE_ORDER
from deckforge_core.schemas.extracted import ExtractedDeck, ExtractedSlide
from deckforge_core.schemas.pack import FormatPack, StyleProfile


@dataclass
class AnalysisReport:
    """Summary of :func:`analyse_decks` for the CLI's "learn" report."""

    deck_count: int
    slide_count: int
    archetype_counts: dict[str, int]
    style: StyleProfile
    clusters: list[DiscoveredCluster]
    new_archetypes: list[str]
    aspect_ratios: list[str] = field(default_factory=list)


def _all_slides(decks: list[ExtractedDeck]) -> list[ExtractedSlide]:
    return [slide for deck in decks for slide in deck.slides]


def _aspect_ratios(decks: list[ExtractedDeck]) -> list[str]:
    return sorted({deck.aspect_ratio for deck in decks if deck.slides})


def _group_by_archetype(slides: list[ExtractedSlide]) -> dict[str, list[ExtractedSlide]]:
    groups: dict[str, list[ExtractedSlide]] = defaultdict(list)
    for slide in slides:
        archetype, _ = detect_archetype(slide)
        groups[archetype].append(slide)
    return dict(groups)


def analyse_decks(decks: list[ExtractedDeck]) -> AnalysisReport:
    """Run detection + clustering + style derivation over extracted decks."""
    slides = _all_slides(decks)
    counts: Counter[str] = Counter()
    labels = None
    clusters: list[DiscoveredCluster] = []
    if slides:
        vectors = embed_slides(slides)
        labels, _ = cluster_slides(vectors)
        clusters = discover_archetypes(slides, labels)
        for slide in slides:
            archetype, _ = detect_archetype(slide)
            counts[archetype] += 1

    return AnalysisReport(
        deck_count=len(decks),
        slide_count=len(slides),
        archetype_counts=dict(sorted(counts.items())),
        style=style_from_decks(decks),
        clusters=clusters,
        new_archetypes=[c.dominant_heuristic_archetype for c in clusters if c.is_new],
        aspect_ratios=_aspect_ratios(decks),
    )


def learn_pack(
    folder: Path,
    name: str,
    *,
    target_dir: Path,
    use_cache: bool = True,
    max_decks: int = 0,
) -> FormatPack:
    """Ingest ``folder`` and build + persist a :class:`FormatPack`.

    ``max_decks`` caps how many extracted decks are analysed (0 = no limit).
    The returned pack is also saved via ``save_pack`` into ``target_dir``.
    """
    result = extract_directory(folder, use_cache=use_cache)
    decks = [deck for deck in result.decks if deck.slides]
    if max_decks > 0:
        decks = decks[:max_decks]

    report = analyse_decks(decks)
    groups = _group_by_archetype(_all_slides(decks))

    detected = sorted(report.archetype_counts)
    default_order = [a for a in ARCHETYPE_ORDER if a in detected]

    pack = FormatPack(
        name=name,
        version="1.0",
        source_deck_count=len(decks),
        source_slide_count=report.slide_count,
        created_at=datetime.now(timezone.utc),
        aspect_ratios=report.aspect_ratios or ["16:9"],
        archetypes=detected,
        default_archetype_order=default_order,
        style=report.style,
    )
    library = blueprints_from_slides(groups, report.style.margins)
    save_pack(pack, library, target_dir)
    return pack

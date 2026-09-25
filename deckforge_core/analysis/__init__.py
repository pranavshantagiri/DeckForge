"""Archetype + style analysis, clustering, blueprint building (Phase 1B).

Public API::

    learn_pack(folder, name, *, target_dir=...)   # folder -> saved FormatPack
    analyse_decks(decks)                          # -> AnalysisReport
    detect_archetype(slide)                       # -> (archetype, confidence)
    style_from_decks(decks)                       # -> StyleProfile
"""

from deckforge_core.analysis.archetype import detect_archetype
from deckforge_core.analysis.blueprint import blueprints_from_slides
from deckforge_core.analysis.build_pack import AnalysisReport, analyse_decks, learn_pack
from deckforge_core.analysis.cluster import (
    CANONICAL_ARCHETYPES,
    DiscoveredCluster,
    cluster_slides,
    discover_archetypes,
    embed_slides,
)
from deckforge_core.analysis.features import (
    FEATURE_DIM,
    FEATURE_NAMES,
    bullet_paragraphs,
    slide_features,
)
from deckforge_core.analysis.style_profile import style_from_decks

__all__ = [
    "AnalysisReport",
    "CANONICAL_ARCHETYPES",
    "DiscoveredCluster",
    "FEATURE_DIM",
    "FEATURE_NAMES",
    "analyse_decks",
    "blueprints_from_slides",
    "bullet_paragraphs",
    "cluster_slides",
    "detect_archetype",
    "discover_archetypes",
    "embed_slides",
    "learn_pack",
    "slide_features",
    "style_from_decks",
]

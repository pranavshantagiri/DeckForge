"""Data contracts shared by every workstream.

These schemas are the frozen contract: ingest emits :class:`ExtractedSlide`,
analysis emits :class:`StyleProfile` + :class:`Blueprint`, the planner emits
:class:`DeckPlan`, and the renderer consumes :class:`DeckPlan` + a
:class:`FormatPack`. Nothing that produces or consumes these may change shape
without a schema version bump here.
"""

from deckforge_core.schemas.archetypes import ARCHETYPE_ORDER, Archetype  # noqa: F401
from deckforge_core.schemas.blueprints import (  # noqa: F401
    AlternateArrangement,
    Blueprint,
    BlueprintLibrary,
    ContentKind,
    SlotDef,
    SlotRegion,
    TextLimits,
)
from deckforge_core.schemas.deck_plan import (  # noqa: F401
    ChartSeries,
    ChartSpec,
    DeckPlan,
    DiagramSpec,
    GraphEdge,
    GraphNode,
    GraphSpec,
    ImageReq,
    PersonSpec,
    SlidePlan,
    SlotValue,
    TableSpec,
)
from deckforge_core.schemas.pack import (  # noqa: F401
    ColorPalette,
    DensityStats,
    FontPair,
    FormatPack,
    Grid,
    ImageTreatment,
    Margins,
    PaletteColor,
    StyleConfidence,
    StyleProfile,
    TypeScale,
    TypeScaleEntry,
)
from deckforge_core.schemas.qa import (  # noqa: F401
    IssueSeverity,
    QACheckType,
    QAIssue,
    QASlideResult,
    QASummaryReport,
)
from deckforge_core.schemas.slot_vocabulary import (  # noqa: F401
    SLOT_VOCABULARY,
    ArchetypeSlots,
    SlotVocEntry,
    all_entries,
    has_vocabulary,
    slots_for,
)

__all__ = [
    "Archetype",
    "ARCHETYPE_ORDER",
    "ColorPalette",
    "DensityStats",
    "FontPair",
    "FormatPack",
    "Grid",
    "ImageTreatment",
    "Margins",
    "PaletteColor",
    "StyleConfidence",
    "StyleProfile",
    "TypeScale",
    "TypeScaleEntry",
    "AlternateArrangement",
    "Blueprint",
    "BlueprintLibrary",
    "ContentKind",
    "SlotDef",
    "SlotRegion",
    "TextLimits",
    "ChartSeries",
    "ChartSpec",
    "DeckPlan",
    "DiagramSpec",
    "GraphEdge",
    "GraphNode",
    "GraphSpec",
    "ImageReq",
    "PersonSpec",
    "SlidePlan",
    "SlotValue",
    "TableSpec",
    "IssueSeverity",
    "QACheckType",
    "QAIssue",
    "QASlideResult",
    "QASummaryReport",
    "ArchetypeSlots",
    "SLOT_VOCABULARY",
    "SlotVocEntry",
    "all_entries",
    "has_vocabulary",
    "slots_for",
]

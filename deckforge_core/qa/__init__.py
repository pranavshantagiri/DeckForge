"""Visual QA loop: render, deterministic checks, vision review, auto-fix.

Importing this package also registers the concrete slide renderers
(:class:`~deckforge_core.qa.renderers.PowerPointCOMRenderer` and
:class:`~deckforge_core.qa.renderers.LibreOfficeRenderer`) with the shared
provider registry, so ``providers.renderer`` / ``RendererAutodetect().resolve``
can construct them once they are installed.
"""

from __future__ import annotations

from deckforge_core.providers import register_renderer
from deckforge_core.qa.autofix import apply_autofix, run_qa_loop
from deckforge_core.qa.checks import (  # noqa: F401
    BANNED_PHRASES,
    check_banned_phrases,
    check_contrast,
    check_empty_placeholders,
    check_min_font,
    check_off_grid,
    check_overlap,
    check_palette,
    run_deterministic,
)
from deckforge_core.qa.renderers import LibreOfficeRenderer, PowerPointCOMRenderer
from deckforge_core.qa.runner import run_qa
from deckforge_core.qa.vision import REVIEW_RUBRIC, VisionResult, VisionReview
from deckforge_core.schemas.qa import (  # noqa: F401
    IssueSeverity,
    QACheckType,
    QAIssue,
    QASlideResult,
    QASummaryReport,
)

QCReport = QASummaryReport  # contract alias: QCReport re-exports schemas.qa

register_renderer(PowerPointCOMRenderer.backend, PowerPointCOMRenderer)
register_renderer(LibreOfficeRenderer.backend, LibreOfficeRenderer)

__all__ = [
    "BANNED_PHRASES",
    "IssueSeverity",
    "LibreOfficeRenderer",
    "PowerPointCOMRenderer",
    "QACheckType",
    "QAIssue",
    "QASlideResult",
    "QASummaryReport",
    "QCReport",
    "REVIEW_RUBRIC",
    "VisionResult",
    "VisionReview",
    "apply_autofix",
    "check_banned_phrases",
    "check_contrast",
    "check_empty_placeholders",
    "check_min_font",
    "check_off_grid",
    "check_overlap",
    "check_palette",
    "run_deterministic",
    "run_qa",
    "run_qa_loop",
]

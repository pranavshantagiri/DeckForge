"""Top-level QA runner: pick a renderer, run the fix loop, return a report.

No exception escapes to the caller for any QA failure path — everything is
captured into the report's ``qa_log``. When no renderer exists, deterministic
checks still run and the report is marked ``rendered=False``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from deckforge_core.logging_util import get_logger
from deckforge_core.providers import NoneRenderer
from deckforge_core.providers.render import RenderBackend, RendererAutodetect
from deckforge_core.qa.autofix import _build_report, run_qa_loop
from deckforge_core.qa.checks import run_deterministic
from deckforge_core.schemas.blueprints import BlueprintLibrary
from deckforge_core.schemas.deck_plan import DeckPlan
from deckforge_core.schemas.pack import FormatPack
from deckforge_core.schemas.qa import QASummaryReport

log = get_logger("deckforge.qa.runner")


def run_qa(
    deck_plan: DeckPlan,
    pack: FormatPack,
    library: BlueprintLibrary,
    *,
    render_backend: str = "auto",
    out_dir,
    vision=None,
    max_iters: Optional[int] = None,
) -> QASummaryReport:
    """Render the deck, run checks (+ vision), auto-fix and re-render up to the
    configured cap, and return a QA summary report."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    qa_log: list[str] = []

    try:
        renderer = RendererAutodetect().resolve(render_backend)
    except Exception as exc:
        qa_log.append(
            f"render backend {render_backend!r} unavailable ({exc}); "
            "running deterministic checks only"
        )
        renderer = NoneRenderer()

    if renderer.backend != RenderBackend.NONE:
        try:
            if max_iters is None:
                from deckforge_core.config import Settings

                max_iters = int(Settings().get("max_qa_iterations", 3))
            _plan, report = run_qa_loop(
                deck_plan,
                pack,
                library,
                renderer,
                out_dir / "deck.pptx",
                max_iters=max_iters,
                vision=vision,
            )
            return report
        except Exception as exc:
            qa_log.append(
                f"QA render/correction loop failed ({exc}); running deterministic checks only"
            )

    plan = deck_plan.model_copy(deep=True)
    issued = run_deterministic(pack.style, plan, library)
    return _build_report(
        plan,
        pack,
        None,
        [],
        issued,
        vision,
        qa_log,
        1,
        rendered_flag=False,
    )

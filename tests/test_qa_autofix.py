"""Auto-fix + re-render loop (Workstream H)."""

from __future__ import annotations

from deckforge_core.providers._registry import NoneRenderer
from deckforge_core.qa.autofix import apply_autofix, run_qa_loop
from deckforge_core.qa.checks import run_deterministic
from deckforge_core.schemas.archetypes import Archetype
from deckforge_core.schemas.blueprints import (
    Blueprint,
    BlueprintLibrary,
    ContentKind,
    SlotDef,
    SlotRegion,
)
from deckforge_core.schemas.deck_plan import DeckPlan, SlidePlan, SlotValue
from deckforge_core.schemas.qa import IssueSeverity, QACheckType


def _slot(name, x, y, w, h, style="body", kinds=None, optional=False):
    return SlotDef(
        name=name,
        kinds=kinds or [ContentKind.TEXT],
        region=SlotRegion(x=x, y=y, w=w, h=h),
        style=style,
        optional=optional,
    )


def _library() -> BlueprintLibrary:
    return BlueprintLibrary(
        [
            Blueprint(
                id="two-column-text",
                archetype=Archetype.TWO_COLUMN_TEXT,
                slots=[
                    _slot("title", 0.06, 0.05, 0.88, 0.1, "h2"),
                    _slot("body", 0.08, 0.28, 0.42, 0.2, "body", kinds=[ContentKind.LIST]),
                    _slot("optional_card", 0.55, 0.5, 0.4, 0.2, "body", optional=True),
                ],
            )
        ]
    )


def _overflow_plan() -> DeckPlan:
    return DeckPlan(
        title="Overflow",
        aspect_ratio="16:9",
        pack="demo",
        slides=[
            SlidePlan(
                n=1,
                archetype="two-column-text",
                title="A big list",
                slots={
                    "title": SlotValue(text="A big list"),
                    "body": SlotValue(items=[f"bullet item number {i}" for i in range(60)]),
                    "optional_card": SlotValue(),
                },
            )
        ],
    )


def _clean_plan() -> DeckPlan:
    return DeckPlan(
        title="Clean",
        aspect_ratio="16:9",
        pack="demo",
        slides=[
            SlidePlan(
                n=1,
                archetype="two-column-text",
                title="Clean slide",
                slots={
                    "title": SlotValue(text="Clean slide"),
                    "body": SlotValue(items=["one point", "two points", "three points"]),
                },
            )
        ],
    )


def _empty_required_plan() -> DeckPlan:
    return DeckPlan(
        title="Missing content",
        aspect_ratio="16:9",
        pack="demo",
        slides=[
            SlidePlan(
                n=1,
                archetype="two-column-text",
                title="Missing body",
                slots={"title": SlotValue(text="Missing body")},
            )
        ],
    )


# --------------------------------------------------------------------------- #
# apply_autofix
# --------------------------------------------------------------------------- #
def test_overflow_fix_shortens_and_clears_error(canonical_style):
    plan = _overflow_plan()
    issues = run_deterministic(canonical_style, plan, _library())
    overflow = [i for i in issues[1] if i.check == QACheckType.OVERFLOW]
    assert len(overflow) == 1
    assert overflow[0].severity == IssueSeverity.ERROR

    new_plan, changed, log = apply_autofix(plan, issues, _library(), pack=canonical_style)
    assert changed is True
    assert any("shortened" in entry for entry in log)

    rerun = run_deterministic(canonical_style, new_plan, _library())
    assert not [i for i in rerun[1] if i.check == QACheckType.OVERFLOW]
    assert len(new_plan.slides[0].slots["body"].items) < 60


def test_required_empty_slot_gets_placeholder_fill(canonical_style):
    plan = _empty_required_plan()
    issues = run_deterministic(canonical_style, plan, _library())
    empties = [i for i in issues[1] if i.check == QACheckType.EMPTY_PLACEHOLDER]
    assert empties and empties[0].detail and empties[0].detail["slot"] == "body"

    new_plan, changed, log = apply_autofix(plan, issues, _library(), pack=canonical_style)
    assert changed is True
    assert any("placeholder-fill" in entry for entry in log)
    assert not new_plan.slides[0].slots["body"].is_empty

    rerun = run_deterministic(canonical_style, new_plan, _library())
    assert not [i for i in rerun[1] if i.check == QACheckType.EMPTY_PLACEHOLDER]


def test_autofix_removes_empty_optional_slot(canonical_style):
    plan = _overflow_plan()  # optional_card is left empty everywhere
    issues = run_deterministic(canonical_style, plan, _library())
    new_plan, changed, log = apply_autofix(plan, issues, _library(), pack=canonical_style)
    assert changed is True
    assert any("removed empty optional slot" in entry for entry in log)
    assert "optional_card" not in new_plan.slides[0].slots


def test_autofix_clean_plan_is_noop(canonical_style):
    plan = _clean_plan()
    issues = {1: []}
    new_plan, changed, log = apply_autofix(plan, issues, _library(), pack=canonical_style)
    assert changed is False
    assert log == []
    assert new_plan.slides[0].slots == plan.slides[0].slots


# --------------------------------------------------------------------------- #
# run_qa_loop
# --------------------------------------------------------------------------- #
def test_run_qa_loop_converges_clean_plan(canonical_pack, tmp_path):
    renderer = NoneRenderer()
    final_plan, report = run_qa_loop(
        _clean_plan(), canonical_pack, _library(), renderer,
        tmp_path / "deck.pptx", max_iters=1,
    )
    assert final_plan.title == "Clean"
    assert report.iterations_used == 1
    assert report.errors_total() == 0
    assert len(report.slides) == 1


def test_run_qa_loop_fixes_overflow_and_rerenders(canonical_pack, tmp_path):
    renderer = NoneRenderer()
    final_plan, report = run_qa_loop(
        _overflow_plan(), canonical_pack, _library(), renderer,
        tmp_path / "deck.pptx", max_iters=3,
    )
    assert report.errors_total() == 0
    assert report.iterations_used >= 2
    assert any("shortened" in entry for entry in report.qa_log)
    assert final_plan.slides[0].slots["body"].items != _overflow_plan().slides[0].slots["body"].items


def test_run_qa_loop_honours_max_iters_cap(canonical_pack, tmp_path):
    # even an unfixable plan cannot exceed the cap of 3 iterations
    renderer = NoneRenderer()
    _plan, report = run_qa_loop(
        _overflow_plan(), canonical_pack, _library(), renderer,
        tmp_path / "deck.pptx", max_iters=3,
    )
    assert report.iterations_used <= 3

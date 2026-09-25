import tempfile
from pathlib import Path

from deckforge_core.config import Settings
from deckforge_core.planner import (
    PlannerOptions,
    TemplatePlanner,
    plan_deck,
)
from deckforge_core.schemas.slot_vocabulary import slots_for


def test_template_planner_validates(canonical_pack):
    tpl = TemplatePlanner()
    plan = tpl.plan("Test topic for planning", canonical_pack, PlannerOptions(slide_count=10))
    # Should validate
    assert plan is not None
    assert len(plan.slides) == 10
    # Check aspect ratio
    assert plan.aspect_ratio == "16:9"


def test_all_slides_use_canonical_slots(canonical_pack):
    tpl = TemplatePlanner()
    plan = tpl.plan("Test topic", canonical_pack, PlannerOptions(slide_count=10))
    for slide in plan.slides:
        voc_names = set(slots_for(slide.archetype).names())
        slide_names = set(slide.slots.keys())
        # All slide keys subset of voc names
        assert slide_names.issubset(voc_names), f"Slide {slide.n} has invalid keys"


def test_three_distinct_archetypes(canonical_pack):
    tpl = TemplatePlanner()
    plan = tpl.plan("Test topic", canonical_pack, PlannerOptions(slide_count=10))
    archetypes = set(s.archetype for s in plan.slides)
    assert len(archetypes) >= 3


def test_no_banned_phrases(canonical_pack):
    tpl = TemplatePlanner()
    plan = tpl.plan("Test topic", canonical_pack, PlannerOptions(slide_count=10))
    from deckforge_core.planner.lint import lint_deck_plan

    issues = lint_deck_plan(plan)
    banned = [i for i in issues if i.check == "banned-phrase"]
    assert len(banned) == 0


def test_aspect_ratio_passthrough(canonical_pack):
    tpl = TemplatePlanner()
    plan = tpl.plan("Test topic", canonical_pack, PlannerOptions(slide_count=10, aspect_ratio="4:3"))
    assert plan.aspect_ratio == "4:3"


def test_agenda_has_three_items(canonical_pack):
    tpl = TemplatePlanner()
    plan = tpl.plan("Test topic", canonical_pack, PlannerOptions(slide_count=10))
    # Find agenda slide
    agenda = [s for s in plan.slides if s.archetype == "agenda"]
    assert len(agenda) > 0
    items = agenda[0].slots.get("items")
    assert items and items.items
    assert len(items.items) >= 3


def test_plan_deck_local_only_returns_valid(canonical_pack):
    with tempfile.TemporaryDirectory() as td:
        settings = Settings(root=Path(td))
        settings.set("local_only", True)
        plan = plan_deck("Test topic", canonical_pack, settings=settings)
        assert plan is not None
        assert len(plan.slides) > 0

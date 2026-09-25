"""Automatic fixes for QA findings + the render -> check -> fix loop.

Deterministic fixes only: shorten overflowing text, fill required empty slots,
drop empty optional slots. Everything else is logged as informational, so the
loop always converges (it stops as soon as autofix makes no change).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from deckforge_core.logging_util import get_logger
from deckforge_core.providers.render import RenderBackend, RenderedSlide
from deckforge_core.qa.checks import run_deterministic, text_overflows
from deckforge_core.qa.vision import VisionReview
from deckforge_core.renderer import render_deck
from deckforge_core.renderer.canvas import canvas_size
from deckforge_core.schemas.blueprints import BlueprintLibrary
from deckforge_core.schemas.deck_plan import DeckPlan, SlotValue
from deckforge_core.schemas.pack import FormatPack, StyleProfile
from deckforge_core.schemas.qa import QACheckType, QAIssue, QASlideResult, QASummaryReport

log = get_logger("deckforge.qa.autofix")


def _slide_by_n(plan: DeckPlan, number: int):
    return next((slide for slide in plan.slides if slide.n == number), None)


def _drop_last_sentence(text: str) -> str:
    pieces = text.rsplit(". ", 1)
    if len(pieces) == 2 and pieces[0].strip():
        return pieces[0]
    words = text.split()
    return " ".join(words[:-3]) if len(words) > 3 else text


def _shorten_value(value: SlotValue, slot_def, pack: StyleProfile, canvas_w: int, canvas_h: int) -> None:
    """Trim text/paragraphs/items until the slot no longer overflows."""
    for _ in range(100):
        if not text_overflows(pack, slot_def, value, canvas_w, canvas_h):
            return
        if value.text:
            if "." in value.text:
                value.text = _drop_last_sentence(value.text)
                continue
            break
        if value.paragraphs and len(value.paragraphs) > 1:
            value.paragraphs = value.paragraphs[:-1]
            continue
        if value.paragraphs and len(value.paragraphs) == 1:
            if "." in value.paragraphs[0]:
                value.paragraphs = [_drop_last_sentence(value.paragraphs[0])]
                continue
            break
        if value.items and len(value.items) > 1:
            value.items = value.items[:-1]
            continue
        break


def _fix_overflow(slide, issue: QAIssue, library, pack, aspect: str, log_entries: list[str]) -> bool:
    slot_name = (issue.detail or {}).get("slot")
    if not slot_name:
        return False
    slots = _library_slots(library, slide.archetype, aspect)
    slot_def = next((slot for slot in slots if slot.name == slot_name), None)
    value = slide.slots.get(slot_name)
    if slot_def is None or value is None:
        return False
    canvas_w, canvas_h = canvas_size(aspect)
    before = value.model_dump()
    _shorten_value(value, slot_def, pack, canvas_w, canvas_h)
    if value.model_dump() == before:
        return False
    log_entries.append(f"autofix: shortened {slot_name!r} on slide {slide.n} to fit")
    return True


def _library_slots(library: BlueprintLibrary, archetype: str, aspect: str) -> list:
    try:
        _blueprint, slots = library.resolve(archetype, aspect)
    except KeyError:
        return []
    return slots


def _fill_required(slide, issue: QAIssue, log_entries: list[str]) -> bool:
    slot_name = (issue.detail or {}).get("slot")
    if not slot_name:
        return False
    topic = slide.title or slide.archetype or "topic"
    label = " ".join(word.capitalize() for word in slot_name.replace("_", " ").split())
    slide.slots[slot_name] = SlotValue(text=f"{label} pending: {topic}")
    log_entries.append(f"autofix: placeholder-fill required slot {slot_name!r} (slide {slide.n})")
    return True


def apply_autofix(
    plan: DeckPlan,
    issues: dict[int, list[QAIssue]],
    library: BlueprintLibrary,
    *,
    pack: Optional[StyleProfile] = None,
) -> tuple[DeckPlan, bool, list[str]]:
    """Return ``(new_plan, changed, log)`` after deterministic fixes."""
    new_plan = plan.model_copy(deep=True)
    changed = False
    log_entries: list[str] = []
    aspect = plan.aspect_ratio or "16:9"

    for slide in new_plan.slides:
        by_name = {slot.name: slot for slot in _library_slots(library, slide.archetype, aspect)}
        for name, value in list(slide.slots.items()):
            slot_def = by_name.get(name)
            if (
                slot_def is not None
                and slot_def.optional
                and (value is None or value.is_empty)
            ):
                del slide.slots[name]
                log_entries.append(f"autofix: removed empty optional slot {name!r} (slide {slide.n})")
                changed = True

    for number in sorted(issues):
        slide = _slide_by_n(new_plan, number)
        if slide is None:
            continue
        for issue in issues[number]:
            if issue.check == QACheckType.EMPTY_PLACEHOLDER:
                changed = _fill_required(slide, issue, log_entries) or changed
            elif issue.severity.value == "error":
                if issue.check == QACheckType.OVERFLOW:
                    changed = _fix_overflow(slide, issue, library, pack, aspect, log_entries) or changed
                else:
                    log_entries.append(
                        f"qa: {issue.check.value} slide {number} has no deterministic autofix"
                    )
            else:
                log_entries.append(f"qa: {issue.check.value} slide {number} noted (no autofix)")
    return new_plan, changed, log_entries


# --------------------------------------------------------------------------- #
# Report assembly
# --------------------------------------------------------------------------- #
def _build_report(
    plan: DeckPlan,
    pack: FormatPack,
    out_pptx: Optional[Path],
    rendered: list[RenderedSlide],
    issued: dict[int, list[QAIssue]],
    vision: Optional[VisionReview],
    qa_log: list[str],
    iterations_used: int,
    *,
    rendered_flag: bool = True,
) -> QASummaryReport:
    by_number = {item.number: item for item in rendered}
    slides: list[QASlideResult] = []
    for slide in plan.slides:
        rendered_slide = by_number.get(slide.n)
        thumbnail = rendered_slide.image_path if (rendered_slide and rendered_slide.image_path) else None
        review = None
        if thumbnail and vision is not None and vision.available:
            review = vision.review(thumbnail)
        slides.append(
            QASlideResult(
                slide_n=slide.n,
                thumbnail_path=thumbnail,
                issues=sorted(
                    issued.get(slide.n, []), key=lambda issue: issue.severity.value
                ),
                vision_review=review.text if review else None,
                vision_score=review.score if review else None,
            )
        )
    errors = sum(len(result.errors()) for result in slides)
    return QASummaryReport(
        pack=pack.name,
        deck_path=str(out_pptx) if out_pptx else None,
        rendered=rendered_flag,
        slides=slides,
        iterations_used=iterations_used,
        qa_log=list(qa_log),
        vision_model=vision.model if vision is not None else None,
        passed=errors == 0,
    )


# --------------------------------------------------------------------------- #
# Render -> check -> fix loop
# --------------------------------------------------------------------------- #
def run_qa_loop(
    deck_plan: DeckPlan,
    pack: FormatPack,
    library: BlueprintLibrary,
    renderer,
    out_pptx,
    *,
    max_iters: int = 3,
    vision: Optional[VisionReview] = None,
) -> tuple[DeckPlan, QASummaryReport]:
    """Render, run checks (and vision), autofix errors, re-render; return the
    final plan plus a QA report with per-slide results and the fix iterations."""
    max_iters = max(1, min(int(max_iters), 3))
    plan = deck_plan.model_copy(deep=True)
    qa_log: list[str] = []
    if vision is None:
        vision = VisionReview(None)
    out_pptx = Path(out_pptx)
    renders_dir = out_pptx.parent / "renders"

    report: Optional[QASummaryReport] = None
    for iteration in range(1, max_iters + 1):
        render_deck(plan, pack, library, out_pptx, warnings=qa_log)
        rendered = renderer.render(out_pptx, renders_dir)
        issued = run_deterministic(pack.style, plan, library)
        report = _build_report(
            plan,
            pack,
            out_pptx,
            rendered,
            issued,
            vision,
            qa_log,
            iteration,
            rendered_flag=renderer.backend != RenderBackend.NONE,
        )
        if report.errors_total() == 0 or iteration >= max_iters:
            return plan, report
        new_plan, changed, fix_log = apply_autofix(plan, issued, library, pack=pack.style)
        qa_log.extend(fix_log)
        if not changed:
            return plan, report
        plan = new_plan
    assert report is not None
    return plan, report

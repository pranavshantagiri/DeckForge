"""Anti-AI copy lint (Workstream D)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from deckforge_core.schemas.deck_plan import DeckPlan, SlotValue

BANNED_PHRASES: list[str] = [
    "delve",
    "unlock",
    "in today's fast-paced world",
    "game-changer",
    "seamless",
    "leverage",
    "landscape",
    "testament",
    "cutting-edge",
    "revolutioniz(e|ing)",
    "best-in-class",
    "synergy",
    "at the end of the day",
    "think outside the box",
    "drill down",
    "going forward",
    "hit the ground running",
]


TOPIC_STYLE_TITLES = [
    "Overview",
    "Agenda",
    "Introduction",
    "Updates",
    "Next Steps",
    "Summary",
    "Background",
    "About",
    "Detail",
]


REPLACEMENTS: dict[str, str] = {
    "leverage": "use",
    "seamless": "smooth",
    "utilize": "use",
    "delve": "look",
    "unlock": "gain",
}


@dataclass
class LintIssue:
    check: str
    message: str
    slide_n: Optional[int] = None
    severity: str = "warning"  # warning | error


def _make_word_boundary_pattern(phrase: str) -> re.Pattern[str]:
    # Handle regex-like entries if any
    if "(" in phrase or "|" in phrase or "\\" in phrase:
        try:
            return re.compile(rf"\b{phrase}\b", re.IGNORECASE)
        except re.error:
            return re.compile(re.escape(phrase), re.IGNORECASE)
    return re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)


BANNED_PATTERNS: list[re.Pattern[str]] = [_make_word_boundary_pattern(p) for p in BANNED_PHRASES]


def _has_banned(text: str) -> list[LintIssue]:
    issues: list[LintIssue] = []
    if not text:
        return issues
    for pattern in BANNED_PATTERNS:
        if pattern.search(text):
            match = pattern.search(text)
            phrase = match.group(0) if match else pattern.pattern
            issues.append(
                LintIssue(
                    check="banned-phrase",
                    message=f"banned phrase detected: {phrase}",
                    severity="warning",
                )
            )
    return issues


def _count_em_dashes(text: str) -> int:
    if not text:
        return 0
    # Count em dash characters
    return text.count("—")


def _starts_with_emoji_bullet(line: str) -> bool:
    line = line.strip()
    if not line:
        return False
    # Bullet markers
    if line.startswith(("-", "*", "•")):
        content = line.lstrip("-*•").lstrip()
    else:
        content = line
    if not content:
        return False
    # Check for emoji (basic Unicode ranges)
    ch = content[0]
    # Common emoji ranges
    if 0x1F300 <= ord(ch) <= 0x1F5FF:  # Misc Symbols and Pictographs
        return True
    if 0x1F600 <= ord(ch) <= 0x1F64F:  # Emoticons
        return True
    if 0x1F680 <= ord(ch) <= 0x1F6FF:  # Transport and Map
        return True
    if 0x1F700 <= ord(ch) <= 0x1FAFF:  # Symbols and other
        return True
    if 0x2600 <= ord(ch) <= 0x26FF:  # Misc symbols
        return True
    if 0x2700 <= ord(ch) <= 0x27BF:  # Dingbats
        return True
    return False


def _first_three_words(text: str) -> str:
    if not text:
        return ""
    tokens = re.findall(r"\b\w+\b", text)
    if len(tokens) < 3:
        return " ".join(tokens).lower()
    return " ".join(tokens[:3]).lower()


def _repeated_opener_issues(lines: list[str]) -> list[LintIssue]:
    issues: list[LintIssue] = []
    openers: dict[str, int] = {}
    for line in lines:
        if not line or not line.strip():
            continue
        opener = _first_three_words(line)
        if not opener:
            continue
        openers[opener] = openers.get(opener, 0) + 1
    for opener, count in openers.items():
        if count >= 3:
            issues.append(
                LintIssue(
                    check="repeated-opener",
                    message=f"repeated opener {opener!r} used {count} times",
                    severity="warning",
                )
            )
    return issues


def lint_text(text: str, *, extra_banned: tuple[str, ...] = ()) -> list[LintIssue]:
    issues: list[LintIssue] = []
    if not text:
        return issues

    for phrase in extra_banned:
        if re.search(rf"\b{re.escape(phrase)}\b", text, re.IGNORECASE):
            issues.append(
                LintIssue(
                    check="banned-phrase",
                    message=f"banned phrase detected: {phrase}",
                    severity="warning",
                )
            )

    issues.extend(_has_banned(text))

    # em-dash overuse: >2 em dashes per paragraph
    if _count_em_dashes(text) > 2:
        issues.append(
            LintIssue(
                check="em-dash-overuse",
                message="em-dash overuse (>2 per paragraph)",
                severity="warning",
            )
        )

    # Check for emoji bullets (if the whole text is a bullet line)
    if _starts_with_emoji_bullet(text):
        issues.append(
            LintIssue(
                check="emoji-bullet",
                message="emoji bullet detected",
                severity="warning",
            )
        )

    # repeated opener across paragraphs within this text blob
    issues.extend(_repeated_opener_issues(text.splitlines()))

    return issues


def _is_topic_style_title(title: Optional[str]) -> bool:
    if not title:
        return False
    t = title.strip()
    # Check exact matches or prefix matches
    for candidate in TOPIC_STYLE_TITLES:
        if t == candidate or t.startswith(candidate + " "):
            # Must be just the word or word + minimal
            if len(t) <= len(candidate) + 20:  # allow short suffix
                return True
    return False


def lint_deck_plan(plan: DeckPlan, *, extra_banned: tuple[str, ...] = ()) -> list[LintIssue]:
    issues_all: list[LintIssue] = []

    for slide in plan.slides:
        slide_issues: list[LintIssue] = []
        # Check title
        if _is_topic_style_title(slide.title):
            slide_issues.append(
                LintIssue(
                    check="topic-style-title",
                    message=f"topic-style title: {slide.title}",
                    slide_n=slide.n,
                    severity="warning",
                )
            )
        if slide.title:
            for issue in lint_text(slide.title, extra_banned=extra_banned):
                issue.slide_n = slide.n
                slide_issues.append(issue)

        # Check all slot values
        for slot_name, slot_value in slide.slots.items():
            slide_issues.extend(_lint_slot_value(slot_value, slide.n, extra_banned))

        issues_all.extend(slide_issues)

    # Density guard
    if plan.word_count > 600:
        issues_all.append(
            LintIssue(
                check="density",
                message=f"word count {plan.word_count} > 600",
                severity="warning",
            )
        )

    return issues_all


def _lint_slot_value(
    slot_value: SlotValue, slide_n: int, extra_banned: tuple[str, ...]
) -> list[LintIssue]:
    issues: list[LintIssue] = []

    if slot_value.text:
        for issue in lint_text(slot_value.text, extra_banned=extra_banned):
            issue.slide_n = slide_n
            issues.append(issue)

    if slot_value.paragraphs:
        for i, p in enumerate(slot_value.paragraphs):
            for issue in lint_text(p, extra_banned=extra_banned):
                issue.slide_n = slide_n
                issues.append(issue)
        for issue in _repeated_opener_issues(slot_value.paragraphs):
            issue.slide_n = slide_n
            issues.append(issue)

    if slot_value.items:
        for item in slot_value.items:
            for issue in lint_text(item, extra_banned=extra_banned):
                issue.slide_n = slide_n
                issues.append(issue)
            if _starts_with_emoji_bullet(item):
                issues.append(
                    LintIssue(
                        check="emoji-bullet",
                        message="emoji bullet detected",
                        slide_n=slide_n,
                        severity="warning",
                    )
                )

    return issues


def _collapse_repeated_openers(text: str) -> str:
    if not text:
        return text
    lines = text.splitlines()
    openers: dict[str, int] = {}
    for line in lines:
        if line.strip():
            opener = _first_three_words(line)
            if opener:
                openers[opener] = openers.get(opener, 0) + 1
    if not any(count >= 3 for count in openers.values()):
        return text
    new_lines = []
    for line in lines:
        if not line.strip():
            new_lines.append(line)
            continue
        opener = _first_three_words(line)
        if opener and openers.get(opener, 0) >= 3:
            words = re.findall(r"\b\w+\b", line)
            if len(words) >= 3:
                new_line = " ".join(words[3:]).strip()
                if new_line:
                    new_lines.append(new_line)
                    continue
        new_lines.append(line)
    return "\n".join(new_lines) if new_lines else text


def _fix_text(text: str) -> str:
    if not text:
        return text
    fixed = text
    # Apply replacements (case-insensitive for the key)
    for bad, good in REPLACEMENTS.items():
        # Word boundary replacement
        fixed = re.sub(rf"\b{re.escape(bad)}\b", good, fixed, flags=re.IGNORECASE)

    # Strip emojis from bullet lines
    lines = fixed.splitlines()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("-", "*", "•")):
            content = stripped.lstrip("-*•").lstrip()
            if content:
                ch = content[0]
                # Remove emoji if at start
                is_emoji = False
                if 0x1F300 <= ord(ch) <= 0x1FAFF or 0x2600 <= ord(ch) <= 0x27BF:
                    is_emoji = True
                if is_emoji:
                    # Remove the emoji char(s) - simple approach
                    content_fixed = content[1:].lstrip()
                    line_fixed = stripped[0] + " " + content_fixed
                    new_lines.append(line_fixed)
                    continue
        new_lines.append(line)
    fixed = "\n".join(new_lines) if new_lines else fixed

    # collapse repeated openers
    collapsed = _collapse_repeated_openers(fixed)
    return collapsed


def autofix_issues(plan: DeckPlan) -> tuple[DeckPlan, bool]:
    changed = False
    new_slides = []

    for slide in plan.slides:
        slide_changed = False
        new_slots: dict[str, SlotValue] = {}

        # Fix title
        new_title = slide.title
        if new_title:
            fixed_title = _fix_text(new_title)
            if fixed_title != new_title:
                new_title = fixed_title
                slide_changed = True

        # Fix slots
        for slot_name, slot_value in slide.slots.items():
            new_slot = slot_value.model_copy(deep=True)
            slot_mod = False

            if new_slot.text:
                fixed = _fix_text(new_slot.text)
                if fixed != new_slot.text:
                    new_slot.text = fixed
                    slot_mod = True

            if new_slot.paragraphs:
                new_paras = []
                for p in new_slot.paragraphs:
                    fixed = _fix_text(p)
                    new_paras.append(fixed)
                    if fixed != p:
                        slot_mod = True
                new_slot.paragraphs = new_paras

            if new_slot.items:
                new_items = []
                for item in new_slot.items:
                    fixed = _fix_text(item)
                    new_items.append(fixed)
                    if fixed != item:
                        slot_mod = True
                new_slot.items = new_items

            new_slots[slot_name] = new_slot
            if slot_mod:
                slide_changed = True

        # Handle repeated openers across paragraphs in the whole slide?
        # Collapse repeated openers (drop the duplicated opener phrase) - simple heuristic
        if not slide_changed:
            # quick check - skip complex for now
            pass

        new_slide = slide.model_copy(
            update={"title": new_title, "slots": new_slots}
        )
        new_slides.append(new_slide)
        if slide_changed or new_slide != slide:
            changed = True

    new_plan = plan.model_copy(update={"slides": new_slides})
    return new_plan, changed

"""Approximate text fitting: shrink-to-fit + line estimation.

Deliberately approximate: average latin glyph width is modelled as a constant
fraction of the point size (0.52 for lowercase-heavy text, 0.6 for uppercase),
then a greedy word-wrap estimates the block height. Exactness comes later from
QA rendering (Workstream H).
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

EMU_PER_PT = 12700

_LOWER_FACTOR = 0.52
_UPPER_FACTOR = 0.6
_FLOOR_PT = 9.0
_STEP_PT = 0.5


def _char_factor(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return _LOWER_FACTOR
    uppercase = sum(1 for c in letters if c.isupper())
    return _UPPER_FACTOR if uppercase / len(letters) > 0.5 else _LOWER_FACTOR


def wrap_text(text: str, size_pt: float, width_emu: int) -> List[str]:
    """Greedy word-wrap ``text`` to ``width_emu`` at ``size_pt``."""
    max_chars = max(1, int(width_emu / (_char_factor(text) * size_pt * EMU_PER_PT)))
    lines: List[str] = []
    for raw in text.split("\n"):
        words = raw.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if len(candidate) <= max_chars or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def estimate_block_height(text: str, size_pt: float, width_emu: int, line_spacing: float) -> int:
    """Estimated rendered height in EMU of ``text`` wrapped to ``width_emu``."""
    lines = wrap_text(text, size_pt, width_emu)
    return int(round(len(lines) * size_pt * line_spacing * EMU_PER_PT))


def _block_height(
    text_items: Sequence[str], size_pt: float, width_emu: int, line_spacing: float
) -> int:
    return sum(
        estimate_block_height(t, size_pt, width_emu, line_spacing) for t in text_items
    )


def fit_paragraphs(
    text_items: Sequence[str],
    style_entry,
    box_width_emu: int,
    box_height_emu: int,
    allowed_sizes_pt: Optional[Sequence[float]] = None,
) -> Tuple[float, bool, List[str]]:
    """Return ``(size_pt, overflow, lines)`` for text that fits ``box_*_emu``.

    Starts at ``style_entry.size_pt`` and steps down in 0.5pt increments to a
    floor of 9pt. ``allowed_sizes_pt`` (if given) restricts the candidate
    sizes. ``overflow`` is True when even the smallest candidate still exceeds
    the box; the returned ``size_pt`` is then that smallest candidate.
    """
    start = float(style_entry.size_pt)
    line_spacing = float(style_entry.line_spacing)

    if allowed_sizes_pt:
        candidates = [float(s) for s in allowed_sizes_pt]
        candidates = [s for s in candidates if s <= start + 1e-9]
        if not candidates:
            candidates = [start]
    else:
        candidates = []
        size = start
        while size >= _FLOOR_PT - 1e-9:
            candidates.append(round(size, 2))
            size -= _STEP_PT

    last_size = start
    for size in candidates:
        last_size = size
        if _block_height(text_items, size, box_width_emu, line_spacing) <= box_height_emu:
            lines = [line for t in text_items for line in wrap_text(t, size, box_width_emu)]
            return size, False, lines

    lines = [line for t in text_items for line in wrap_text(t, last_size, box_width_emu)]
    return last_size, True, lines

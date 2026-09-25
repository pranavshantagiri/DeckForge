"""Vision-model review of rendered slide thumbnails.

Optional and offline-skippable: without a provider that declares the VISION
capability *and* exposes ``describe_image``, :class:`VisionReview` stays
inactive and every review call just returns ``None``. The module imports cleanly
even when no third-party SDK (e.g. anthropic) is registered.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

from deckforge_core.logging_util import get_logger
from deckforge_core.providers.base import Capability

log = get_logger("deckforge.qa.vision")

REVIEW_RUBRIC = """Review this slide thumbnail as a meticulous design QA lead.
Score each dimension from 0 (broken) to 1 (excellent):

1. Hierarchy - is there an obvious visual order (headline -> body -> caption)?
2. Balance - do the regions feel balanced, and is whitespace deliberate?
3. Density - is the copy comfortably dense, neither sparse nor wall-of-text?
4. Consistency - does it look like part of the same deck/pack as its siblings?
5. Off-palette - are all colors inside the pack palette (no clashing hues)?
6. Overflow - is any text clipped, cut off, or visibly spilling its box?

End your reply with a single line: score: 0.XX"""


class VisionResult(BaseModel):
    text: str = ""
    score: float = 0.5


class VisionReview:
    """Reviews a rendered thumbnail with a vision-capable LLM provider."""

    def __init__(self, provider=None) -> None:
        self.model: Optional[str] = None
        self._provider = provider
        active = provider is not None and provider.supports(Capability.VISION)
        self._active = bool(active and hasattr(provider, "describe_image"))
        if self._active:
            self.model = getattr(provider, "default_model", "") or getattr(
                provider, "name", ""
            )

    @property
    def available(self) -> bool:
        return self._active

    def review(self, image_path, rubric: Optional[str] = None) -> Optional[VisionResult]:
        """Review a thumbnail PNG; returns None when no vision provider is active."""
        if not self._active or not image_path:
            return None
        try:
            text = self._provider.describe_image(
                str(image_path), prompt=rubric or REVIEW_RUBRIC
            )
        except Exception as exc:  # pragma: no cover - depends on external API
            log.warning("vision review failed: %s", exc)
            return None
        return VisionResult(text=str(text), score=_extract_score(str(text)))


def _extract_score(text: str) -> float:
    """Pull ``score: 0.XX`` / ``N/10`` / ``NN%`` out of a review reply."""
    if not text:
        return 0.5
    match = re.search(r"score\s*[:=]?\s*(\d+(?:\.\d+)?)\s*/\s*10", text, re.I)
    if match:
        return max(0.0, min(1.0, float(match.group(1)) / 10.0))
    match = re.search(r"score\s*[:=]?\s*([01](?:\.\d+)?)", text, re.I)
    if match:
        return max(0.0, min(1.0, float(match.group(1))))
    match = re.search(r"(\d{1,3})\s*%", text)
    if match:
        return max(0.0, min(1.0, int(match.group(1)) / 100.0))
    return 0.5

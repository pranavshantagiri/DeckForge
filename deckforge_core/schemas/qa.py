"""QA report schemas: deterministic + vision checks produce a per-image report
and a summary. Nothing here is rendered to the user as a stack trace; the GUI/
CLI read these models."""

from __future__ import annotations

import enum
from typing import Optional

from pydantic import BaseModel, Field


class IssueSeverity(str, enum.Enum):
    ERROR = "error"  # must be fixed (overflow, overlap)
    WARNING = "warning"  # should be fixed (off-grid, contrast, weak hierarchy)
    INFO = "info"  # cosmetic / informational


class QACheckType(str, enum.Enum):
    OVERFLOW = "overflow"
    OVERLAP = "overlap"
    OFF_GRID = "off-grid"
    CONTRAST = "contrast"
    MIN_FONT = "min-font"
    IMAGE_RES = "image-resolution"
    EMPTY_PLACEHOLDER = "empty-placeholder"
    OFF_PALETTE = "off-palette"
    OFF_FONT = "off-font"
    BANNED_PHRASE = "banned-phrase"
    HIERARCHY = "hierarchy"
    DENSITY = "density"
    BALANCE = "balance"
    CONSISTENCY = "consistency"


class QAIssue(BaseModel):
    check: QACheckType
    severity: IssueSeverity = IssueSeverity.WARNING
    slide_n: int = Field(ge=1)
    message: str
    detail: Optional[dict] = None
    fix: Optional[str] = None


class QASlideResult(BaseModel):
    slide_n: int = Field(ge=1)
    thumbnail_path: Optional[str] = None
    issues: list[QAIssue] = Field(default_factory=list)
    vision_review: Optional[str] = None
    vision_score: Optional[float] = None  # 0..1

    def errors(self) -> list[QAIssue]:
        return [i for i in self.issues if i.severity == IssueSeverity.ERROR]

    def warnings(self) -> list[QAIssue]:
        return [i for i in self.issues if i.severity == IssueSeverity.WARNING]


class QASummaryReport(BaseModel):
    pack: str
    deck_path: Optional[str] = None
    rendered: bool = False
    slides: list[QASlideResult] = Field(default_factory=list)
    iterations_used: int = Field(default=1, ge=1, le=3)
    qa_log: list[str] = Field(default_factory=list)
    vision_model: Optional[str] = None
    passed: bool = True

    def errors_total(self) -> int:
        return sum(len(s.errors()) for s in self.slides)

    def warnings_total(self) -> int:
        return sum(len(s.warnings()) for s in self.slides)

    def unresolved(self) -> list[QAIssue]:
        return [i for s in self.slides for i in s.issues]

    @property
    def passed_check(self) -> bool:
        return self.passed and self.errors_total() == 0

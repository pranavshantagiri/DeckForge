"""Slide rendering to images (for QA + previews).

PowerPoint COM gives the truest rendering on Windows when PowerPoint is
installed; LibreOffice headless is the fallback. Auto-detection prefers COM,
then LibreOffice. RichClient refuses to exist: this module never blocks a
headless build when neither is available — RendererAutodetect reports NONE.
"""

from __future__ import annotations

import shutil
from abc import abstractmethod
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from deckforge_core.errors import RendererError
from deckforge_core.logging_util import get_logger
from deckforge_core.providers.base import Provider

log = get_logger("deckforge.providers.render")


class RenderBackend(str, Enum):
    AUTO = "auto"
    POWERPOINT_COM = "powerpoint-com"
    LIBREOFFICE = "libreoffice"
    NONE = "none"


class RenderedSlide(BaseModel):
    number: int  # 1-based slide number
    image_path: str
    width_px: int = 0
    height_px: int = 0
    error: Optional[str] = None


class SlideRenderer(Provider):
    provider_type = "render"
    backend: RenderBackend = RenderBackend.NONE

    @abstractmethod
    def render(
        self,
        pptx_path: Path,
        out_dir: Path,
        *,
        slides: Optional[list[int]] = None,
        dpi: int = 96,
    ) -> list[RenderedSlide]:
        """Render every slide (or the requested ones) to PNG in ``out_dir``.

        Returns one :class:`RenderedSlide` per rendered slide, in order. Errors
        are captured per slide, never raised, so QA can proceed on the rest.
        """

    def healthcheck(self) -> str:
        return f"{self.backend.value} renderer"

    @staticmethod
    def detect() -> bool:
        raise NotImplementedError


def _soffice_path() -> Optional[Path]:
    for candidate in shutil.which("soffice"), shutil.which("libreoffice"):
        if candidate:
            return Path(candidate)
    win_candidates = [
        Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
        Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
    ]
    for cand in win_candidates:
        if cand.exists():
            return cand
    return None


def powerpoint_com_available() -> bool:
    """True when pywin32 and PowerPoint are both installed."""
    try:
        import win32com.client  # noqa: F401
        from win32com.client import Dispatch  # noqa: F401
    except Exception:
        return False
    try:
        import pythoncom  # noqa: F401
    except Exception:
        return False
    # Registry check mirrors where POWERPNT.EXE registers itself.
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\POWERPNT.EXE",
        ):
            return True
    except OSError:
        return False


def libreoffice_available() -> bool:
    return _soffice_path() is not None


class RendererAutodetect:
    """Decides which backends exist on this machine."""

    def __init__(self) -> None:
        self.com = powerpoint_com_available()
        self.libreoffice = libreoffice_available()

    @property
    def available(self) -> list[RenderBackend]:
        backends: list[RenderBackend] = []
        if self.com:
            backends.append(RenderBackend.POWERPOINT_COM)
        if self.libreoffice:
            backends.append(RenderBackend.LIBREOFFICE)
        if not backends:
            backends.append(RenderBackend.NONE)
        return backends

    def resolve(self, preferred: str = RenderBackend.AUTO.value) -> SlideRenderer:
        from deckforge_core.providers import _registry

        if preferred != RenderBackend.AUTO.value:
            try:
                backend = RenderBackend(preferred)
            except ValueError as exc:
                raise RendererError(f"unknown render backend {preferred!r}") from exc
            if backend == RenderBackend.NONE:
                return _registry.NoneRenderer()
            cls = _registry.RENDERER_CLASSES.get(backend)
            if cls is None or not cls.available():
                raise RendererError(
                    f"render backend {backend.value} requested but not installed"
                )
            return cls()
        picked = self.available[0]
        cls = _registry.RENDERER_CLASSES.get(picked)
        if cls is None:
            raise RendererError("no renderer available on this machine")
        return cls()

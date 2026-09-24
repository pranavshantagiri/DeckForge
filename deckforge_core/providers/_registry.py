"""Provider registry.

Populated by the workstreams that implement concrete providers. Provider
creation is lazy so missing SDKs never break core imports. Also supplies the
no-op renderer used when the machine has no PowerPoint nor LibreOffice.
"""

from __future__ import annotations

from pathlib import Path

from deckforge_core.logging_util import get_logger
from deckforge_core.providers.base import Provider
from deckforge_core.providers.images import ImageProvider
from deckforge_core.providers.llm import LLMProvider
from deckforge_core.providers.render import (  # noqa: F401
    RenderBackend,
    RendererAutodetect,
    SlideRenderer,
)

log = get_logger("deckforge.providers")

# keyed by provider name
LLM_CLASSES: dict[str, type[LLMProvider]] = {}
IMAGE_CLASSES: dict[str, type[ImageProvider]] = {}
RENDERER_CLASSES: dict[RenderBackend, type[SlideRenderer]] = {}

_singletons: dict[str, Provider] = {}


def register_llm(name: str, cls: type[LLMProvider]) -> None:
    LLM_CLASSES[name] = cls


def register_image(name: str, cls: type[ImageProvider]) -> None:
    IMAGE_CLASSES[name] = cls


def register_renderer(backend: RenderBackend, cls: type[SlideRenderer]) -> None:
    RENDERER_CLASSES[backend] = cls


def llm_provider(name: str, **kwargs) -> LLMProvider:
    cls = LLM_CLASSES.get(name)
    if cls is None:
        raise ValueError(f"LLM provider {name!r} not registered")
    return cls(**kwargs)


def image_provider(name: str, **kwargs) -> ImageProvider:
    cls = IMAGE_CLASSES.get(name)
    if cls is None:
        raise ValueError(f"image provider {name!r} not registered")
    return cls(**kwargs)


def renderer(backend: RenderBackend = RenderBackend.AUTO) -> SlideRenderer:

    return RendererAutodetect().resolve(backend.value)


def singleton(key: str, factory) -> Provider:
    if key not in _singletons:
        _singletons[key] = factory()
    return _singletons[key]


class NoneRenderer(SlideRenderer):
    """No-op renderer for machines with neither PowerPoint nor LibreOffice.

    Every slide reports an error so downstream QA/review can explain to the
    user why no thumbnails exist instead of crashing.
    """

    name = "none"
    backend = RenderBackend.NONE

    def render(self, pptx_path, out_dir, *, slides=None, dpi=96):
        from deckforge_core.providers.render import RenderedSlide

        out_dir.mkdir(parents=True, exist_ok=True)
        file_path = Path(pptx_path)
        if not file_path.exists():
            return [
                RenderedSlide(number=1, image_path="", error=f"{file_path} missing")
            ]
        # python-pptx only to learn the slide count without Office installed
        from pptx import Presentation

        try:
            prs = Presentation(str(file_path))
        except Exception as exc:  # pragma: no cover
            return [RenderedSlide(number=1, image_path="", error=str(exc))]
        numbers = list(range(1, len(prs.slides) + 1))
        if slides:
            numbers = [n for n in numbers if n in set(slides)]
        return [
            RenderedSlide(
                number=n,
                image_path="",
                error="no renderer installed (powerpoint-com or libreoffice)",
            )
            for n in numbers
        ]


register_renderer(RenderBackend.NONE, NoneRenderer)

"""Provider interfaces and registry. Nothing SDK-specific is imported here."""

from deckforge_core.providers import _registry  # noqa: F401
from deckforge_core.providers._registry import (  # noqa: F401
    IMAGE_CLASSES,
    LLM_CLASSES,
    RENDERER_CLASSES,
    NoneRenderer,
    image_provider,
    llm_provider,
    register_image,
    register_llm,
    register_renderer,
    renderer,
)
from deckforge_core.providers.base import Capability, Provider  # noqa: F401
from deckforge_core.providers.images import (  # noqa: F401
    ImageItem,
    ImageProvider,
)
from deckforge_core.providers.llm import (  # noqa: F401
    LLMProvider,
    LLMResult,
    Message,
    MockLLMProvider,
    TokenUsage,
)
from deckforge_core.providers.render import (  # noqa: F401
    RenderBackend,
    RenderedSlide,
    RendererAutodetect,
    SlideRenderer,
)

register_llm("mock", MockLLMProvider)

__all__ = [
    "Capability",
    "Provider",
    "ImageItem",
    "ImageProvider",
    "LLMProvider",
    "LLMResult",
    "Message",
    "MockLLMProvider",
    "TokenUsage",
    "RenderBackend",
    "RendererAutodetect",
    "RenderedSlide",
    "SlideRenderer",
    "NoneRenderer",
    "register_llm",
    "register_image",
    "register_renderer",
    "llm_provider",
    "image_provider",
    "renderer",
    "LLM_CLASSES",
    "IMAGE_CLASSES",
    "RENDERER_CLASSES",
]

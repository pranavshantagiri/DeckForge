"""Provider interfaces (LLM, images, rendering).

Each provider abstracts a single capability behind a small ABC. All providers
are optional at runtime: the app works fully local-only, and providers are
imported lazily so a missing SDK never breaks import of the core.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod


class Capability(str, enum.Enum):
    COMPLETE = "complete"  # chat / text completion
    STRUCTURED = "structured"  # validated structured output
    VISION = "vision"  # can reason over images
    IMAGE_SEARCH = "image-search"
    IMAGE_FETCH = "image-fetch"
    RENDER = "render"  # pptx -> png


class Provider(ABC):
    """Base contract. ``name`` is the stable identifier used in settings/config
    ("anthropic", "unsplash", "powerpoint-com")."""

    provider_type: str = "base"
    name: str = ""
    capabilities: set[Capability] = set()

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities

    @abstractmethod
    def healthcheck(self) -> str:
        """Return a short human-readable health string or raise ProviderError."""

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<{type(self).__name__} name={self.name!r}>"

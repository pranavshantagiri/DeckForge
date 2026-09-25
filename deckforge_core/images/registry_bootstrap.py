"""Registers the image providers and a convenience factory.

Importing this module has no side effects beyond populating the provider
registry (idempotent). API keys are resolved from :class:`SecretStore` at
construction time, so building a provider is always cheap and never fails;
missing keys surface only when ``search`` is actually called.
"""

from __future__ import annotations

from deckforge_core.config import SecretStore
from deckforge_core.images.providers import PexelsProvider, UnsplashProvider
from deckforge_core.providers import IMAGE_CLASSES, register_image

_DEFAULT_ORDER = ("unsplash", "pexels")


def bootstrap_image_providers() -> None:
    """Register Unsplash and Pexels in the shared provider registry."""
    register_image("unsplash", UnsplashProvider)
    register_image("pexels", PexelsProvider)


def _default_provider_name() -> str:
    for name in _DEFAULT_ORDER:
        if SecretStore().get(name):
            return name
    return _DEFAULT_ORDER[0]


def image_provider_for(name: str | None = None, **kwargs):
    """Build an image provider by name.

    With ``name`` missing/empty the first key-configured provider is chosen
    (falling back to ``unsplash``), so key-less construction still works.
    Registrations are bootstrapped lazily and keys are resolved per call.
    """
    bootstrap_image_providers()
    selected = name or _default_provider_name()
    cls = IMAGE_CLASSES.get(selected)
    if cls is None:
        raise ValueError(f"image provider {selected!r} not registered")
    return cls(**kwargs)

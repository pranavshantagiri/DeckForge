"""Interface tests: provider contracts behave as advertised."""

from __future__ import annotations

from pathlib import Path

import pytest

from deckforge_core.errors import DeckForgeError, LocalOnlyError
from deckforge_core.providers import (
    ImageItem,
    RendererAutodetect,
    llm_provider,
    renderer,
)
from deckforge_core.providers.base import Capability
from deckforge_core.providers.llm import Message, MockLLMProvider
from deckforge_core.providers.render import RenderBackend
from deckforge_core.schemas.deck_plan import DeckPlan
from deckforge_core.schemas.pack import StyleProfile


def test_mock_llm_registered():
    provider = llm_provider("mock")
    assert isinstance(provider, MockLLMProvider)


def test_mock_llm_completes():
    provider = MockLLMProvider()
    result = provider.complete(
        [Message(role="user", content="Summarize DeckForge in one line.")]
    )
    assert result.text.startswith("[mock:")
    assert provider.total_spend() >= 0.0


def test_mock_llm_structured_when_capable():
    provider = MockLLMProvider()
    # mock does not declare STRUCTURED, so the base class wraps it in a JSON
    # prompt and (inevitably for mock) fails -> must raise LLMError, not crash.
    with pytest.raises(Exception) as excinfo:
        provider.complete_structured(
            [Message(role="user", content="plan a deck")], DeckPlan
        )
    assert "structured output failed" in str(excinfo.value)


def test_illicit_local_only_raises():
    class _Flaky(LocalOnlyError):
        pass

    with pytest.raises(DeckForgeError):
        raise _Flaky("no network in local-only mode")


def test_renderer_autodetect_shape():
    det = RendererAutodetect()
    assert det.available  # at least one entry (NONE guaranteed)
    assert RenderBackend.NONE in det.available or det.com or det.libreoffice


def test_noop_renderer_returns_per_slide_errors():
    r = renderer(RenderBackend.NONE)
    from deckforge_core.providers.render import RenderedSlide

    out = r.render(Path("does-not-exist.pptx"), Path("."))
    assert isinstance(out[0], RenderedSlide)
    assert out[0].error


def test_image_item_model():
    item = ImageItem(
        id="p1", provider="unsplash", url="https://x/1.jpg",
        width=1600, height=1200, license="Unsplash", attribution="Photo by A on Unsplash",
    )
    assert item.width > 0
    assert item.attribution


def test_capability_flags():
    assert MockLLMProvider.supports(MockLLMProvider, Capability.COMPLETE) is False
    # Mock declares no capabilities (not vision/structured), base default is set()


def test_style_profile_importable():
    assert StyleProfile is not None

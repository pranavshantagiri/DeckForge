
import pytest

from deckforge_core.providers._registry import llm_provider
from deckforge_core.providers.llm import LLMProvider, LLMResult, Message
from deckforge_core.providers.llm_anthropic import AnthropicProvider
from deckforge_core.providers.llm_local import LocalProvider
from deckforge_core.providers.registry_bootstrap import bootstrap_providers
from deckforge_core.schemas.deck_plan import DeckPlan


@pytest.fixture(autouse=True)
def setup_providers():
    bootstrap_providers()
    yield


def test_bootstrap_registers_anthropic():
    p = llm_provider("anthropic")
    assert isinstance(p, AnthropicProvider)


def test_anthropic_construction_no_api_key_ok():
    p = AnthropicProvider()
    assert p.name == "anthropic"


def test_pricing_sanity():
    # opus > sonnet input price
    from deckforge_core.planner.pricing import ANTHROPIC_PRICING
    sonnet = ANTHROPIC_PRICING["claude-sonnet-5"][0]
    opus = ANTHROPIC_PRICING["claude-opus-5-5"][0]
    assert opus > sonnet


def test_local_provider_raises_on_complete():
    lp = LocalProvider()
    with pytest.raises(Exception):  # LLMError
        lp.complete([Message(role="user", content="hi")])


class _FakeStructured(LLMProvider):
    name = "fake"
    default_model_name = "fake-1"
    call_count = 0

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.call_count = 0

    def complete(
        self,
        messages,
        *,
        model=None,
        temperature=0.7,
        max_tokens=4096,
    ) -> LLMResult:
        self.call_count += 1
        if self.call_count == 1:
            # Return bad JSON
            bad = "{ bad json"
            usage = self.record_usage(model or self.default_model, 10, 10)
            return LLMResult(text=bad, usage=usage)
        # Return valid small DeckPlan JSON
        plan_json = '''
        {
          "title": "Test",
          "aspect_ratio": "16:9",
          "created_by": "test",
          "pack": "demo",
          "slides": [
            {
              "n": 1,
              "archetype": "title",
              "title": "Test",
              "slots": {"title": {"text": "Test"}}
            }
          ]
        }
        '''
        usage = self.record_usage(model or self.default_model, 10, 10)
        return LLMResult(text=plan_json, usage=usage)


def test_structured_repair():
    fake = _FakeStructured()
    result = fake.complete_structured(
        [Message(role="user", content="make plan")],
        output_model=DeckPlan,
    )
    assert isinstance(result, DeckPlan)
    assert result.title == "Test"

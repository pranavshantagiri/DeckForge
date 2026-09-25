"""Provider registry bootstrap (Workstream D)."""

from __future__ import annotations

from deckforge_core.config import Settings
from deckforge_core.errors import LLMError
from deckforge_core.providers._registry import llm_provider as get_llm_provider
from deckforge_core.providers._registry import register_llm
from deckforge_core.providers.llm import LLMProvider


def bootstrap_providers() -> None:
    try:
        from deckforge_core.providers.llm_anthropic import AnthropicProvider
        register_llm("anthropic", AnthropicProvider)
    except Exception:
        pass

    try:
        from deckforge_core.providers.llm_openai import OpenAIProvider
        register_llm("openai", OpenAIProvider)
    except Exception:
        pass

    try:
        from deckforge_core.providers.llm_gemini import GeminiProvider
        register_llm("gemini", GeminiProvider)
    except Exception:
        pass

    try:
        from deckforge_core.providers.llm_local import LocalProvider
        register_llm("local", LocalProvider)
    except Exception:
        pass


def available_llm_names() -> list[str]:
    from deckforge_core.providers._registry import LLM_CLASSES

    return sorted(LLM_CLASSES.keys())


def default_llm(settings: Settings, db=None) -> LLMProvider:
    provider_name = settings.get("llm_provider") or "mock"
    bootstrap_providers()
    try:
        provider = get_llm_provider(provider_name, db=db)
        return provider
    except Exception as exc:
        raise LLMError(f"failed to instantiate provider {provider_name}: {exc}")

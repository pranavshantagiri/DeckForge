"""Gemini LLM provider (Workstream D)."""

from __future__ import annotations

from typing import Optional

from deckforge_core.config import SecretStore
from deckforge_core.errors import LLMError
from deckforge_core.providers.base import Capability
from deckforge_core.providers.llm import LLMProvider, LLMResult, Message


class GeminiProvider(LLMProvider):
    name = "gemini"
    default_model_name = "gemini-2.5-pro"
    capabilities = {Capability.COMPLETE, Capability.STRUCTURED}

    price_input_per_1m = 1.25
    price_output_per_1m = 10.0
    price_cache_read_per_1m = 0.125

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        db=None,
    ) -> None:
        super().__init__(model=model, db=db)
        self.api_key = api_key if api_key is not None else SecretStore().get("gemini")

    def complete(
        self,
        messages: list[Message],
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResult:
        try:
            import google.generativeai as genai
        except Exception as exc:
            raise LLMError(f"google-generativeai SDK not installed: {exc}")

        if not self.api_key:
            raise LLMError("gemini API key not found")

        genai.configure(api_key=self.api_key)
        model_name = model or self.default_model
        gemini_model = genai.GenerativeModel(model_name)

        parts = []
        for m in messages:
            content = m.content if isinstance(m.content, str) else str(m.content)
            parts.append(content)

        try:
            response = gemini_model.generate_content("\n\n".join(parts))
        except Exception as exc:
            raise LLMError(f"gemini complete failed: {exc}")

        text = response.text if hasattr(response, "text") else str(response)

        usage = self.record_usage(model_name, input_tokens=len(text.split()), output_tokens=len(text.split()))
        return LLMResult(text=text, usage=usage, finish_reason="complete")

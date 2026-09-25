"""OpenAI LLM provider (Workstream D)."""

from __future__ import annotations

from typing import Any, Optional

from deckforge_core.config import SecretStore
from deckforge_core.errors import LLMError
from deckforge_core.providers.base import Capability
from deckforge_core.providers.llm import LLMProvider, LLMResult, Message, T_co


class OpenAIProvider(LLMProvider):
    name = "openai"
    default_model_name = "gpt-5"
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
        self.api_key = api_key if api_key is not None else SecretStore().get("openai")

    def complete(
        self,
        messages: list[Message],
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResult:
        try:
            import openai
        except Exception as exc:
            raise LLMError(f"openai SDK not installed: {exc}")

        if not self.api_key:
            raise LLMError("openai API key not found")

        client = openai.OpenAI(api_key=self.api_key)
        model_name = model or self.default_model

        chat_messages: list[dict[str, Any]] = []
        for m in messages:
            chat_messages.append({"role": m.role, "content": m.content if isinstance(m.content, str) else str(m.content)})

        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=chat_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            raise LLMError(f"openai complete failed: {exc}")

        text = ""
        if response.choices:
            choice = response.choices[0]
            if hasattr(choice, "message") and choice.message:
                text = choice.message.content or ""

        input_tokens = 0
        output_tokens = 0
        if hasattr(response, "usage"):
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

        usage = self.record_usage(model_name, input_tokens, output_tokens)
        return LLMResult(text=text, usage=usage, finish_reason=getattr(response.choices[0], "finish_reason", "") if response.choices else "")

    def complete_structured(
        self,
        messages: list[Message],
        output_model: type[T_co],
        *,
        model: Optional[str] = None,
        temperature: float = 0.4,
        max_tokens: int = 4096,
    ) -> T_co:
        return super().complete_structured(
            messages, output_model, model=model, temperature=temperature, max_tokens=max_tokens
        )

"""LLM provider implementations (Workstream D)."""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any, Optional

from deckforge_core.config import SecretStore
from deckforge_core.errors import LLMError
from deckforge_core.providers.base import Capability
from deckforge_core.providers.llm import (
    LLMProvider,
    LLMResult,
    Message,
    T_co,
)


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    default_model_name = "claude-sonnet-5"
    capabilities = {Capability.COMPLETE, Capability.STRUCTURED, Capability.VISION}

    price_input_per_1m = 3.0
    price_output_per_1m = 15.0
    price_cache_read_per_1m = 0.30

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        db=None,
    ) -> None:
        super().__init__(model=model, db=db)
        self.api_key = api_key if api_key is not None else SecretStore().get("anthropic")

    def complete(
        self,
        messages: list[Message],
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResult:
        try:
            import anthropic
        except Exception as exc:
            raise LLMError(f"anthropic SDK not installed: {exc}")

        if not self.api_key:
            raise LLMError("anthropic API key not found")

        client = anthropic.Anthropic(api_key=self.api_key)
        model_name = model or self.default_model

        # Split system messages
        system_parts: list[str] = []
        user_assistant: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                if isinstance(m.content, str):
                    system_parts.append(m.content)
                else:
                    system_parts.append(str(m.content))
            else:
                user_assistant.append({"role": m.role, "content": m.content if isinstance(m.content, str) else str(m.content)})

        system = "\n\n".join(system_parts) if system_parts else None

        try:
            response = client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=user_assistant,
            )
        except Exception as exc:
            raise LLMError(f"anthropic complete failed: {exc}")

        text = ""
        if hasattr(response, "content") and response.content:
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text

        input_tokens = 0
        output_tokens = 0
        cache_read = 0
        if hasattr(response, "usage"):
            input_tokens = getattr(response.usage, "input_tokens", 0)
            output_tokens = getattr(response.usage, "output_tokens", 0)
            cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or getattr(response.usage, "cache_read_tokens", 0)

        usage = self.record_usage(
            model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
        )

        return LLMResult(text=text, usage=usage, finish_reason=getattr(response, "stop_reason", ""))

    def complete_structured(
        self,
        messages: list[Message],
        output_model: type[T_co],
        *,
        model: Optional[str] = None,
        temperature: float = 0.4,
        max_tokens: int = 4096,
    ) -> T_co:
        # Use base class approach with JSON instruction
        return super().complete_structured(
            messages,
            output_model,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def describe_image(self, image_path: str, prompt: str) -> str:
        try:
            import anthropic
            from PIL import Image
        except Exception as exc:
            raise LLMError(f"required deps missing for vision: {exc}")

        if not self.api_key:
            raise LLMError("anthropic API key not found")

        try:
            img = Image.open(image_path)
            max_dim = 1024
            if img.width > max_dim or img.height > max_dim:
                scale = max_dim / max(img.width, img.height)
                new_size = (int(img.width * scale), int(img.height * scale))
                img = img.resize(new_size, Image.LANCZOS)
            buffer = BytesIO()
            img.save(buffer, format="JPEG")
            b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        except Exception as exc:
            raise LLMError(f"failed to process image: {exc}")

        client = anthropic.Anthropic(api_key=self.api_key)
        model_name = self.default_model

        try:
            response = client.messages.create(
                model=model_name,
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": b64,
                                },
                            },
                        ],
                    }
                ],
            )
        except Exception as exc:
            raise LLMError(f"vision call failed: {exc}")

        text = ""
        if hasattr(response, "content") and response.content:
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
        return text

    def record_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        job: str | None = None,
    ):
        """Cost-account using the tuned pricing table, falling back to class attrs."""
        from deckforge_core.planner.pricing import ANTHROPIC_PRICING

        pricing = ANTHROPIC_PRICING.get(model)
        if pricing is not None:
            self.price_input_per_1m, self.price_output_per_1m, self.price_cache_read_per_1m = pricing
        return super().record_usage(
            model,
            input_tokens,
            output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            job=job,
        )

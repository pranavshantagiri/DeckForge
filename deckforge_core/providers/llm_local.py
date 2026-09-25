"""Local LLM provider (Workstream D)."""

from __future__ import annotations

from typing import Optional

from deckforge_core.errors import LLMError
from deckforge_core.providers.base import Capability
from deckforge_core.providers.llm import LLMProvider, LLMResult, Message


class LocalProvider(LLMProvider):
    name = "local"
    default_model_name = "local-model"
    capabilities = {Capability.COMPLETE}

    def __init__(self, model_path: str = "", model: Optional[str] = None, db=None) -> None:
        super().__init__(model=model, db=db)
        self.model_path = model_path

    def complete(
        self,
        messages: list[Message],
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResult:
        raise LLMError("no local model configured")

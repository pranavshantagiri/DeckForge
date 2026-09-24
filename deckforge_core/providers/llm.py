"""LLM provider abstraction.

Implements: text completion, optional structured output (Pydantic), optional
vision input, plus cost/token accounting. Anthropic is the reference
implementation; OpenAI/Gemini/local follow the same interface. A deterministic
MockLLMProvider powers tests and local-only generation.
"""

from __future__ import annotations

import hashlib
import json
import time
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, TypeVar, Union

from pydantic import BaseModel, Field

from deckforge_core.errors import LLMError
from deckforge_core.logging_util import get_logger
from deckforge_core.providers.base import Capability, Provider

if TYPE_CHECKING:  # pragma: no cover
    from deckforge_core.storage.sqlite import Database

log = get_logger("deckforge.providers.llm")

T_co = TypeVar("T_co", bound=BaseModel, covariant=True)


class Message(BaseModel):
    role: str  # system | user | assistant
    content: Union[str, list[dict[str, Any]]] = ""


class TokenUsage(BaseModel):
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


class LLMResult(BaseModel):
    text: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    finish_reason: str = ""


class LLMProvider(Provider):
    """Base for all LLM providers. Providers must keep a running cost ledger."""

    provider_type = "llm"

    # --- pricing in USD per 1M tokens; overridden by each provider ---
    price_input_per_1m: float = 0.0
    price_output_per_1m: float = 0.0
    price_cache_read_per_1m: float = 0.0

    def __init__(self, model: str | None = None, db: "Database | None" = None) -> None:
        self.default_model = model or self.default_model_name
        self._db = db
        self._ledger: list[TokenUsage] = []

    default_model_name: str = ""

    # ---- core API ---------------------------------------------------------
    @abstractmethod
    def complete(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResult:
        """Run a chat completion and return text."""

    def complete_structured(
        self,
        messages: list[Message],
        output_model: type[T_co],
        *,
        model: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 4096,
    ) -> T_co:
        """Complete and parse into a Pydantic model, retrying malformed output.

        Default implementation prompts for strict JSON and reparses; providers
        may override with native structured/tool output.
        """
        if not self.supports(Capability.STRUCTURED):
            prompt = _structured_prompt(output_model, messages)
        else:
            prompt = messages
        last_error: Exception | None = None
        for attempt in range(2):
            result = self.complete(
                prompt, model=model, temperature=temperature, max_tokens=max_tokens
            )
            try:
                return _parse_structured(output_model, result.text)
            except ValueError as exc:
                last_error = exc
                prompt = list(prompt) + [
                    Message(role="assistant", content=result.text),
                    Message(
                        role="user",
                        content=(
                            "Your previous JSON did not validate: "
                            f"{exc}. Return corrected JSON matching the schema only."
                        ),
                    ),
                ]
        raise LLMError(f"structured output failed after retries: {last_error}")

    # ---- accounting ---------------------------------------------------------
    def record_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        job: str | None = None,
    ) -> TokenUsage:
        cost = (
            input_tokens * self.price_input_per_1m
            + output_tokens * self.price_output_per_1m
            + cache_read_tokens * self.price_cache_read_per_1m
        ) / 1_000_000
        usage = TokenUsage(
            provider=self.name,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            cost_usd=cost,
        )
        self._ledger.append(usage)
        if self._db is not None:
            self._db.record_usage(
                self.name, model, input_tokens, output_tokens,
                cache_read_tokens, cost, job,
            )
        return usage

    @property
    def ledger(self) -> list[TokenUsage]:
        return list(self._ledger)

    def total_spend(self) -> float:
        return sum(u.cost_usd for u in self._ledger)

    # ---- helpers ---------------------------------------------------------
    def healthcheck(self) -> str:
        return f"{self.name} (model={self.default_model})"


def _schema_json(output_model: type[T_co]) -> str:
    return json.dumps(output_model.model_json_schema(), default=str)


def _structured_prompt(output_model: type[T_co], messages: list[Message]) -> list[Message]:
    schema = _schema_json(output_model)
    preamble = (
        "Respond with STRICT JSON only that validates against this JSON schema:\n"
        f"{schema}\n"
        "No markdown fences, no commentary."
    )
    return [Message(role="system", content=preamble), *messages]


def _parse_structured(output_model: type[T_co], text: str) -> T_co:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # strip fenced code block
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"response is not valid JSON: {exc}") from exc
    return output_model.model_validate(data)


class MockLLMProvider(LLMProvider):
    """Deterministic provider used for tests and local-only generation.

    Not a real model: ``complete`` returns echoes/templates. Structured outputs
    are produced by naive string templating that MUST be replaced by the real
    planner in :mod:`deckforge_core.planner`.
    """

    name = "mock"
    default_model_name = "mock-1"

    def complete(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResult:
        model = model or self.default_model
        last_content = ""
        for m in messages:
            if isinstance(m.content, str) and m.content:
                last_content = m.content
        digest = hashlib.sha1(last_content.encode()).hexdigest()[:8]
        time.sleep(0.001)
        text = f"[mock:{digest}] {last_content[:400]}"
        self.record_usage(model, input_tokens=len(last_content.split()), output_tokens=10)
        return LLMResult(text=text, usage=self._ledger[-1], finish_reason="mock")

"""LLM client wrapper using PydanticAI + Anthropic."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

import structlog
from pydantic import BaseModel
from pydantic_ai.models.anthropic import AnthropicModelSettings

from verdandi.config import Settings
from verdandi.metrics import llm_tokens_total

if TYPE_CHECKING:
    from pydantic_ai.models.anthropic import AnthropicModel

logger = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """Wrapper around Anthropic Claude API with PydanticAI for structured outputs."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self._model: AnthropicModel | None = None

    @property
    def model(self) -> AnthropicModel:
        if self._model is None:
            from pydantic_ai.models.anthropic import AnthropicModel
            from pydantic_ai.providers.anthropic import AnthropicProvider

            provider = AnthropicProvider(api_key=self.settings.anthropic_api_key)
            self._model = AnthropicModel(
                self.settings.llm_model,
                provider=provider,
            )
        return self._model

    def _build_model_settings(
        self,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AnthropicModelSettings:
        """Build model_settings with Anthropic prompt caching enabled."""
        temp = temperature if temperature is not None else self.settings.llm_temperature
        tokens = max_tokens if max_tokens is not None else self.settings.llm_max_tokens
        return AnthropicModelSettings(
            temperature=temp,
            max_tokens=tokens,
            anthropic_cache_instructions=True,
        )

    def generate(
        self,
        prompt: str,
        response_model: type[T],
        system: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> T:
        """Generate a structured response using Claude + PydanticAI."""
        from pydantic_ai import Agent

        agent = Agent(
            self.model,
            output_type=response_model,
            system_prompt=system or "You are a helpful assistant.",
        )

        model_settings = self._build_model_settings(temperature, max_tokens)

        logger.debug(
            "LLM request",
            model=self.settings.llm_model,
            response_model=response_model.__name__,
        )

        result = agent.run_sync(prompt, model_settings=model_settings)

        # Log usage for cost tracking
        usage = result.usage()
        logger.info(
            "LLM response",
            model=self.settings.llm_model,
            output_type=response_model.__name__,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            cache_read_tokens=usage.cache_read_tokens or 0,
            cache_write_tokens=usage.cache_write_tokens or 0,
        )

        # Record Prometheus token counters
        model_label = self.settings.llm_model
        llm_tokens_total.labels(model=model_label, token_type="request").inc(
            usage.input_tokens or 0
        )
        llm_tokens_total.labels(model=model_label, token_type="response").inc(
            usage.output_tokens or 0
        )
        llm_tokens_total.labels(model=model_label, token_type="cache_read").inc(
            usage.cache_read_tokens or 0
        )
        llm_tokens_total.labels(model=model_label, token_type="cache_write").inc(
            usage.cache_write_tokens or 0
        )

        return result.output

    def generate_text(
        self,
        prompt: str,
        system: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate plain text response (no structured output)."""
        from pydantic_ai import Agent

        agent = Agent(
            self.model,
            output_type=str,
            system_prompt=system or "You are a helpful assistant.",
        )

        model_settings = self._build_model_settings(temperature, max_tokens)

        result = agent.run_sync(prompt, model_settings=model_settings)

        usage = result.usage()
        logger.info(
            "LLM response",
            model=self.settings.llm_model,
            output_type="str",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            cache_read_tokens=usage.cache_read_tokens or 0,
            cache_write_tokens=usage.cache_write_tokens or 0,
        )

        # Record Prometheus token counters
        model_label = self.settings.llm_model
        llm_tokens_total.labels(model=model_label, token_type="request").inc(
            usage.input_tokens or 0
        )
        llm_tokens_total.labels(model=model_label, token_type="response").inc(
            usage.output_tokens or 0
        )
        llm_tokens_total.labels(model=model_label, token_type="cache_read").inc(
            usage.cache_read_tokens or 0
        )
        llm_tokens_total.labels(model=model_label, token_type="cache_write").inc(
            usage.cache_write_tokens or 0
        )

        return result.output

    @property
    def is_available(self) -> bool:
        return bool(self.settings.anthropic_api_key)

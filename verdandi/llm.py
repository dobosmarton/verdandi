"""LLM client wrapper using PydanticAI + Anthropic."""

from __future__ import annotations

from typing import TypeVar

import structlog
from pydantic import BaseModel

from verdandi.config import Settings

logger = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """Wrapper around Anthropic Claude API with PydanticAI for structured outputs."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from pydantic_ai.models.anthropic import AnthropicModel

            self._model = AnthropicModel(
                self.settings.llm_model,
                api_key=self.settings.anthropic_api_key,
            )
        return self._model

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
            result_type=response_model,
            system_prompt=system or "You are a helpful assistant.",
        )

        logger.debug(
            "LLM request",
            model=self.settings.llm_model,
            response_model=response_model.__name__,
        )

        result = agent.run_sync(prompt)
        return result.data

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
            result_type=str,
            system_prompt=system or "You are a helpful assistant.",
        )

        result = agent.run_sync(prompt)
        return result.data

    @property
    def is_available(self) -> bool:
        return bool(self.settings.anthropic_api_key)

"""LLM client wrapper using PydanticAI with multi-provider support.

Uses streaming by default to prevent network idle-timeout disconnections
on long-running requests (e.g., complex structured outputs).

Supported providers: anthropic (default), openai, google.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, TypeVar

import structlog
from pydantic import BaseModel

from verdandi.config import Settings
from verdandi.metrics import llm_tokens_total

if TYPE_CHECKING:
    from pydantic_ai import Agent
    from pydantic_ai.models import Model
    from pydantic_ai.settings import ModelSettings
    from pydantic_ai.usage import RunUsage

logger = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)
# Unbounded TypeVar for the streaming helper (must accept both BaseModel and str)
_OutputT = TypeVar("_OutputT")


async def _run_streamed(
    agent: Agent[None, _OutputT],
    prompt: str,
    model_settings: ModelSettings,
) -> tuple[_OutputT, RunUsage]:
    """Run a PydanticAI agent in streaming mode and return the final output.

    Streaming keeps the TCP connection alive with continuous data flow,
    preventing network-level idle timeouts (~60s on some NAT/routers).
    """
    async with agent.run_stream(prompt, model_settings=model_settings) as stream:
        # Consume the stream — this forces data to flow continuously
        async for _chunk in stream.stream_output():
            pass
        output: _OutputT = await stream.get_output()
        return output, stream.usage()


class LLMClient:
    """Wrapper around LLM APIs with PydanticAI for structured outputs.

    Supports multiple providers via the ``provider_name`` parameter:
    - ``"anthropic"`` (default) — Anthropic Claude
    - ``"openai"`` — OpenAI GPT
    - ``"google"`` — Google Gemini
    """

    def __init__(
        self,
        settings: Settings | None = None,
        provider_name: str = "anthropic",
    ) -> None:
        self.settings = settings or Settings()
        self.provider_name = provider_name
        self._model: Model | None = None

    @property
    def model_name(self) -> str:
        """Return the model identifier string for this provider."""
        if self.provider_name == "openai":
            return self.settings.openai_model
        if self.provider_name == "google":
            return self.settings.google_model
        return self.settings.llm_model

    @property
    def model(self) -> Model:
        if self._model is None:
            self._model = self._create_model()
        return self._model

    def _create_model(self) -> Model:
        """Create the appropriate PydanticAI model based on provider_name."""
        if self.provider_name == "openai":
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider

            openai_prov = OpenAIProvider(api_key=self.settings.openai_api_key)
            return OpenAIChatModel(self.settings.openai_model, provider=openai_prov)

        if self.provider_name == "google":
            from pydantic_ai.models.google import GoogleModel
            from pydantic_ai.providers.google import GoogleProvider

            google_prov = GoogleProvider(api_key=self.settings.google_api_key)
            return GoogleModel(self.settings.google_model, provider=google_prov)

        # Default: Anthropic
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        anthropic_prov = AnthropicProvider(api_key=self.settings.anthropic_api_key)
        return AnthropicModel(self.settings.llm_model, provider=anthropic_prov)

    def _build_model_settings(
        self,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ModelSettings:
        """Build model_settings appropriate for the current provider."""
        temp = temperature if temperature is not None else self.settings.llm_temperature
        tokens = max_tokens if max_tokens is not None else self.settings.llm_max_tokens

        if self.provider_name == "openai":
            from pydantic_ai.models.openai import OpenAIChatModelSettings

            return OpenAIChatModelSettings(temperature=temp, max_tokens=tokens)

        if self.provider_name == "google":
            from pydantic_ai.models.google import GoogleModelSettings

            return GoogleModelSettings(temperature=temp, max_tokens=tokens)

        # Default: Anthropic
        from pydantic_ai.models.anthropic import AnthropicModelSettings

        return AnthropicModelSettings(
            temperature=temp,
            max_tokens=tokens,
            anthropic_cache_instructions=True,
        )

    def _log_and_record_usage(self, output_type: str, usage: RunUsage) -> None:
        """Log LLM usage and record Prometheus token counters."""
        model_label = self.model_name
        logger.info(
            "LLM response",
            model=model_label,
            provider=self.provider_name,
            output_type=output_type,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            cache_read_tokens=usage.cache_read_tokens or 0,
            cache_write_tokens=usage.cache_write_tokens or 0,
        )

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

    def generate(
        self,
        prompt: str,
        response_model: type[T],
        system: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> T:
        """Generate a structured response using PydanticAI.

        Uses streaming to keep the TCP connection alive and prevent
        network-level idle timeouts from killing long-running requests.
        """
        from pydantic_ai import Agent

        agent: Agent[None, T] = Agent(
            self.model,
            output_type=response_model,
            system_prompt=system or "You are a helpful assistant.",
        )

        model_settings = self._build_model_settings(temperature, max_tokens)

        logger.debug(
            "LLM request",
            model=self.model_name,
            provider=self.provider_name,
            response_model=response_model.__name__,
            streaming=True,
        )

        output, usage = asyncio.run(_run_streamed(agent, prompt, model_settings))

        self._log_and_record_usage(response_model.__name__, usage)
        return output

    def generate_text(
        self,
        prompt: str,
        system: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate plain text response (no structured output).

        Uses streaming to keep the TCP connection alive.
        """
        from pydantic_ai import Agent

        agent: Agent[None, str] = Agent(
            self.model,
            output_type=str,
            system_prompt=system or "You are a helpful assistant.",
        )

        model_settings = self._build_model_settings(temperature, max_tokens)

        logger.debug(
            "LLM request",
            model=self.model_name,
            provider=self.provider_name,
            response_model="str",
            streaming=True,
        )

        output, usage = asyncio.run(_run_streamed(agent, prompt, model_settings))

        self._log_and_record_usage("str", usage)
        return output

    @property
    def is_available(self) -> bool:
        if self.provider_name == "openai":
            return bool(self.settings.openai_api_key)
        if self.provider_name == "google":
            return bool(self.settings.google_api_key)
        return bool(self.settings.anthropic_api_key)

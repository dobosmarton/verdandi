"""LLM client wrapper using PydanticAI + Anthropic.

Uses streaming by default to prevent network idle-timeout disconnections
on long-running requests (e.g., complex structured outputs).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, TypeVar

import structlog
from pydantic import BaseModel
from pydantic_ai.models.anthropic import AnthropicModelSettings

from verdandi.config import Settings
from verdandi.metrics import llm_tokens_total

if TYPE_CHECKING:
    from pydantic_ai import Agent
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.usage import RunUsage

logger = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)
# Unbounded TypeVar for the streaming helper (must accept both BaseModel and str)
_OutputT = TypeVar("_OutputT")


def _get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    """Get the running event loop or create a new one."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


async def _run_streamed(
    agent: Agent[None, _OutputT],
    prompt: str,
    model_settings: AnthropicModelSettings,
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

    def _log_and_record_usage(self, output_type: str, usage: RunUsage) -> None:
        """Log LLM usage and record Prometheus token counters."""
        logger.info(
            "LLM response",
            model=self.settings.llm_model,
            output_type=output_type,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            cache_read_tokens=usage.cache_read_tokens or 0,
            cache_write_tokens=usage.cache_write_tokens or 0,
        )

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

    def generate(
        self,
        prompt: str,
        response_model: type[T],
        system: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> T:
        """Generate a structured response using Claude + PydanticAI.

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
            model=self.settings.llm_model,
            response_model=response_model.__name__,
            streaming=True,
        )

        loop = _get_or_create_event_loop()
        output, usage = loop.run_until_complete(_run_streamed(agent, prompt, model_settings))

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
            model=self.settings.llm_model,
            response_model="str",
            streaming=True,
        )

        loop = _get_or_create_event_loop()
        output, usage = loop.run_until_complete(_run_streamed(agent, prompt, model_settings))

        self._log_and_record_usage("str", usage)
        return output

    @property
    def is_available(self) -> bool:
        return bool(self.settings.anthropic_api_key)

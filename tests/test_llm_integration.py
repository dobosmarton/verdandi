"""Integration tests for LLMClient via PydanticAI TestModel.

These tests verify the LLMClient -> PydanticAI wiring without mocking.
TestModel generates synthetic data from JSON schemas (no LLM, just
procedural Python). FunctionModel allows custom response logic.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from verdandi.config import Settings
from verdandi.llm import LLMClient


class _SimpleOutput(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    score: int


class TestLLMClientWithTestModel:
    """Verify LLMClient.generate() works end-to-end with TestModel."""

    def test_generate_structured_output(self) -> None:
        """TestModel generates valid data matching the output schema."""
        from pydantic_ai.models.test import TestModel

        settings = Settings(anthropic_api_key="test-key")
        client = LLMClient(settings)
        client._model = TestModel()  # type: ignore[assignment]

        result = client.generate(
            prompt="Test prompt",
            response_model=_SimpleOutput,
            system="You are a test assistant.",
        )

        assert isinstance(result, _SimpleOutput)
        assert isinstance(result.name, str)
        assert isinstance(result.score, int)

    def test_generate_text_output(self) -> None:
        """TestModel returns a string for plain text generation."""
        from pydantic_ai.models.test import TestModel

        settings = Settings(anthropic_api_key="test-key")
        client = LLMClient(settings)
        client._model = TestModel()  # type: ignore[assignment]

        result = client.generate_text(
            prompt="Test prompt",
            system="You are a test assistant.",
        )

        assert isinstance(result, str)
        assert len(result) > 0

    def test_model_settings_include_cache_instructions(self) -> None:
        """Verify _build_model_settings returns settings with caching enabled."""
        settings = Settings(anthropic_api_key="test-key")
        client = LLMClient(settings)

        ms = client._build_model_settings(temperature=0.5, max_tokens=1024)

        # AnthropicModelSettings is a TypedDict, so use dict access
        assert ms["temperature"] == 0.5
        assert ms["max_tokens"] == 1024
        assert ms["anthropic_cache_instructions"] is True

    def test_model_settings_uses_defaults_from_config(self) -> None:
        """Settings defaults are used when no overrides are provided."""
        settings = Settings(
            anthropic_api_key="test-key",
            llm_temperature=0.3,
            llm_max_tokens=2048,
        )
        client = LLMClient(settings)

        ms = client._build_model_settings()

        assert ms["temperature"] == 0.3
        assert ms["max_tokens"] == 2048

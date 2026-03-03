"""Tests for strategy loader."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from verdandi.models.idea import DiscoveryType
from verdandi.strategy_loader import (
    get_strategy_by_name,
    list_all_strategies,
    load_all_custom_strategies,
    load_builtin_strategies,
    load_strategy_from_yaml,
    strategy_to_yaml,
)

_builtins = load_builtin_strategies()
DISRUPTION_STRATEGY = _builtins["disruption"]
MOONSHOT_STRATEGY = _builtins["moonshot"]


def test_load_valid_strategy_from_yaml(tmp_path: Path) -> None:
    """Test loading a valid strategy from YAML."""
    yaml_content = """
name: "Test Strategy"
discovery_type: "disruption"

discovery_queries:
  - "test query 1"
  - "test query 2"

discovery_perplexity_question: "What is the test question?"

discovery_system_prompt: "You are a test agent."

synthesis_system_prompt: "Synthesize a test idea."

discovery_output_model: "ProblemReport"
"""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text(yaml_content)

    strategy = load_strategy_from_yaml(yaml_file)

    assert strategy.name == "Test Strategy"
    assert strategy.discovery_type == DiscoveryType.DISRUPTION
    assert len(strategy.discovery_queries) == 2
    assert strategy.discovery_queries[0] == "test query 1"
    assert strategy.discovery_perplexity_question == "What is the test question?"
    assert strategy.discovery_system_prompt == "You are a test agent."
    assert strategy.synthesis_system_prompt == "Synthesize a test idea."
    assert strategy.discovery_output_model == "ProblemReport"


def test_load_strategy_with_string_discovery_type(tmp_path: Path) -> None:
    """Test that string discovery_type gets converted to enum."""
    yaml_content = """
name: "Moonshot Test"
discovery_type: "moonshot"
discovery_queries: ["query"]
discovery_perplexity_question: "question"
discovery_system_prompt: "prompt"
synthesis_system_prompt: "synth"
discovery_output_model: "OpportunityReport"
"""
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text(yaml_content)

    strategy = load_strategy_from_yaml(yaml_file)

    assert strategy.discovery_type == DiscoveryType.MOONSHOT


def test_load_strategy_file_not_found() -> None:
    """Test error when file doesn't exist."""
    with pytest.raises(FileNotFoundError):
        load_strategy_from_yaml(Path("/nonexistent/file.yaml"))


def test_load_strategy_invalid_yaml(tmp_path: Path) -> None:
    """Test error when YAML is malformed."""
    yaml_file = tmp_path / "invalid.yaml"
    yaml_file.write_text("{ invalid: yaml: content")

    with pytest.raises(ValueError, match="Invalid YAML"):
        load_strategy_from_yaml(yaml_file)


def test_load_strategy_not_dict(tmp_path: Path) -> None:
    """Test error when YAML doesn't contain a dict."""
    yaml_file = tmp_path / "list.yaml"
    yaml_file.write_text("- item1\n- item2")

    with pytest.raises(ValueError, match="Expected YAML dict"):
        load_strategy_from_yaml(yaml_file)


def test_load_strategy_missing_required_field(tmp_path: Path) -> None:
    """Test error when required field is missing."""
    yaml_content = """
name: "Incomplete"
discovery_type: "disruption"
"""
    yaml_file = tmp_path / "incomplete.yaml"
    yaml_file.write_text(yaml_content)

    with pytest.raises(ValidationError):
        load_strategy_from_yaml(yaml_file)


def test_load_all_custom_strategies_empty(tmp_path: Path) -> None:
    """Test loading from nonexistent directory returns empty list."""
    strategies = load_all_custom_strategies(tmp_path / "nonexistent")

    assert strategies == []


def test_load_all_custom_strategies_success(tmp_path: Path) -> None:
    """Test loading multiple strategies from directory."""
    # Create first strategy
    yaml1 = tmp_path / "strategy1.yaml"
    yaml1.write_text("""
name: "Strategy 1"
discovery_type: "disruption"
discovery_queries: ["q1"]
discovery_perplexity_question: "question"
discovery_system_prompt: "prompt"
synthesis_system_prompt: "synth"
discovery_output_model: "ProblemReport"
""")

    # Create second strategy
    yaml2 = tmp_path / "strategy2.yaml"
    yaml2.write_text("""
name: "Strategy 2"
discovery_type: "moonshot"
discovery_queries: ["q2"]
discovery_perplexity_question: "question"
discovery_system_prompt: "prompt"
synthesis_system_prompt: "synth"
discovery_output_model: "OpportunityReport"
""")

    strategies = load_all_custom_strategies(tmp_path)

    assert len(strategies) == 2
    assert strategies[0].name == "Strategy 1"
    assert strategies[1].name == "Strategy 2"


def test_load_all_custom_strategies_skips_invalid(tmp_path: Path) -> None:
    """Test that invalid files are silently skipped."""
    # Valid strategy
    valid = tmp_path / "valid.yaml"
    valid.write_text("""
name: "Valid"
discovery_type: "disruption"
discovery_queries: ["q"]
discovery_perplexity_question: "?"
discovery_system_prompt: "p"
synthesis_system_prompt: "s"
discovery_output_model: "ProblemReport"
""")

    # Invalid strategy (missing fields)
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("name: Incomplete")

    strategies = load_all_custom_strategies(tmp_path)

    assert len(strategies) == 1
    assert strategies[0].name == "Valid"


def test_get_strategy_by_name_builtin_disruption() -> None:
    """Test getting built-in disruption strategy."""
    strategy = get_strategy_by_name("disruption")

    assert strategy == DISRUPTION_STRATEGY


def test_get_strategy_by_name_builtin_moonshot() -> None:
    """Test getting built-in moonshot strategy."""
    strategy = get_strategy_by_name("moonshot")

    assert strategy == MOONSHOT_STRATEGY


def test_get_strategy_by_name_builtin_case_insensitive() -> None:
    """Test that built-in names are case-insensitive."""
    assert get_strategy_by_name("DISRUPTION") == DISRUPTION_STRATEGY
    assert get_strategy_by_name("Moonshot") == MOONSHOT_STRATEGY


def test_get_strategy_by_name_custom_by_filename(tmp_path: Path) -> None:
    """Test getting custom strategy by filename."""
    custom = tmp_path / "my-strategy.yaml"
    custom.write_text("""
name: "My Custom Strategy"
discovery_type: "disruption"
discovery_queries: ["q"]
discovery_perplexity_question: "?"
discovery_system_prompt: "p"
synthesis_system_prompt: "s"
discovery_output_model: "ProblemReport"
""")

    strategy = get_strategy_by_name("my-strategy", tmp_path)

    assert strategy is not None
    assert strategy.name == "My Custom Strategy"


def test_get_strategy_by_name_custom_by_name(tmp_path: Path) -> None:
    """Test getting custom strategy by name (case-insensitive)."""
    custom = tmp_path / "filename.yaml"
    custom.write_text("""
name: "My Custom Strategy"
discovery_type: "disruption"
discovery_queries: ["q"]
discovery_perplexity_question: "?"
discovery_system_prompt: "p"
synthesis_system_prompt: "s"
discovery_output_model: "ProblemReport"
""")

    strategy = get_strategy_by_name("my custom strategy", tmp_path)

    assert strategy is not None
    assert strategy.name == "My Custom Strategy"


def test_get_strategy_by_name_not_found() -> None:
    """Test that None is returned when strategy not found."""
    strategy = get_strategy_by_name("nonexistent")

    assert strategy is None


def test_list_all_strategies_builtin_only() -> None:
    """Test listing strategies with no custom directory."""
    result = list_all_strategies(None)

    assert len(result["builtin"]) == 2
    assert result["builtin"][0] == DISRUPTION_STRATEGY
    assert result["builtin"][1] == MOONSHOT_STRATEGY
    assert result["custom"] == []


def test_list_all_strategies_with_custom(tmp_path: Path) -> None:
    """Test listing strategies with custom strategies."""
    custom = tmp_path / "custom.yaml"
    custom.write_text("""
name: "Custom"
discovery_type: "disruption"
discovery_queries: ["q"]
discovery_perplexity_question: "?"
discovery_system_prompt: "p"
synthesis_system_prompt: "s"
discovery_output_model: "ProblemReport"
""")

    result = list_all_strategies(tmp_path)

    assert len(result["builtin"]) == 2
    assert len(result["custom"]) == 1
    assert result["custom"][0].name == "Custom"


def test_strategy_to_yaml_roundtrip(tmp_path: Path) -> None:
    """Test converting strategy to YAML and back."""
    # Convert built-in strategy to YAML
    yaml_str = strategy_to_yaml(DISRUPTION_STRATEGY)

    # Parse and verify
    data = yaml.safe_load(yaml_str)
    assert data["name"] == DISRUPTION_STRATEGY.name
    assert data["discovery_type"] == "disruption"  # Enum converted to string

    # Write to file and load back
    yaml_file = tmp_path / "roundtrip.yaml"
    yaml_file.write_text(yaml_str)
    loaded = load_strategy_from_yaml(yaml_file)

    assert loaded == DISRUPTION_STRATEGY

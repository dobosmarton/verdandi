"""Load and validate custom discovery strategies from YAML files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from verdandi.models.idea import DiscoveryType
from verdandi.strategies import DISRUPTION_STRATEGY, MOONSHOT_STRATEGY, DiscoveryStrategy


def load_strategy_from_yaml(path: Path) -> DiscoveryStrategy:
    """Load a strategy from a YAML file.

    Args:
        path: Path to YAML file

    Returns:
        Validated DiscoveryStrategy instance

    Raises:
        FileNotFoundError: If file doesn't exist
        ValidationError: If YAML doesn't match schema
        ValueError: If YAML is malformed
    """
    if not path.exists():
        raise FileNotFoundError(f"Strategy file not found: {path}")

    content = path.read_text(encoding="utf-8")

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {path}: {e}") from e

    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML dict, got {type(data).__name__}")

    # Convert discovery_type string to enum if needed
    if "discovery_type" in data and isinstance(data["discovery_type"], str):
        data["discovery_type"] = DiscoveryType(data["discovery_type"].upper())

    try:
        return DiscoveryStrategy(**data)
    except ValidationError as e:
        raise ValidationError.from_exception_data(
            title=f"Strategy validation failed for {path.name}",
            line_errors=e.errors(),
        ) from e


def load_all_custom_strategies(strategies_dir: Path) -> list[DiscoveryStrategy]:
    """Load all custom strategies from a directory.

    Args:
        strategies_dir: Directory containing .yaml files

    Returns:
        List of validated strategies (may be empty if dir doesn't exist)
    """
    if not strategies_dir.exists():
        return []

    if not strategies_dir.is_dir():
        return []

    strategies: list[DiscoveryStrategy] = []

    for yaml_file in sorted(strategies_dir.glob("*.yaml")):
        try:
            strategy = load_strategy_from_yaml(yaml_file)
            strategies.append(strategy)
        except (FileNotFoundError, ValueError, ValidationError):
            # Skip invalid files silently — let CLI validate command report errors
            continue

    return strategies


def get_strategy_by_name(
    name: str,
    strategies_dir: Path | None = None,
) -> DiscoveryStrategy | None:
    """Get a strategy by name (built-in or custom).

    Args:
        name: Strategy name ("disruption", "moonshot", or custom name)
        strategies_dir: Directory to search for custom strategies (optional)

    Returns:
        Strategy if found, None otherwise
    """
    # Check built-in strategies first
    if name.lower() == "disruption":
        return DISRUPTION_STRATEGY
    if name.lower() == "moonshot":
        return MOONSHOT_STRATEGY

    # Search custom strategies
    if strategies_dir is None:
        return None

    # Try exact filename match
    yaml_path = strategies_dir / f"{name}.yaml"
    if yaml_path.exists():
        try:
            return load_strategy_from_yaml(yaml_path)
        except (ValueError, ValidationError):
            return None

    # Try case-insensitive name match
    custom_strategies = load_all_custom_strategies(strategies_dir)
    for strategy in custom_strategies:
        if strategy.name.lower() == name.lower():
            return strategy

    return None


def list_all_strategies(strategies_dir: Path | None = None) -> dict[str, list[DiscoveryStrategy]]:
    """List all available strategies (built-in + custom).

    Args:
        strategies_dir: Directory to search for custom strategies (optional)

    Returns:
        Dict with "builtin" and "custom" keys
    """
    builtin = [DISRUPTION_STRATEGY, MOONSHOT_STRATEGY]
    custom = load_all_custom_strategies(strategies_dir) if strategies_dir else []

    return {"builtin": builtin, "custom": custom}


def strategy_to_yaml(strategy: DiscoveryStrategy) -> str:
    """Convert a strategy to YAML format.

    Args:
        strategy: Strategy to serialize

    Returns:
        YAML string
    """
    # Convert to dict, replacing enum with string
    data = strategy.model_dump(mode="python")
    data["discovery_type"] = strategy.discovery_type.value.lower()

    return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)

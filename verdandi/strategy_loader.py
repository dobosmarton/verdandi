"""Load and validate discovery strategies from YAML files."""

from __future__ import annotations

import functools
from pathlib import Path

import yaml
from pydantic import ValidationError

from verdandi.models.idea import DiscoveryType
from verdandi.strategies import DiscoveryStrategy

_BUILTIN_NAMES: frozenset[str] = frozenset(("disruption", "moonshot"))


def _builtin_strategies_dir() -> Path:
    """Return path to the bundled strategies directory."""
    return Path(__file__).resolve().parent.parent / "strategies"


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
        data["discovery_type"] = DiscoveryType(data["discovery_type"].lower())

    return DiscoveryStrategy(**data)


@functools.lru_cache(maxsize=1)
def load_builtin_strategies() -> dict[str, DiscoveryStrategy]:
    """Load built-in strategies from bundled YAML files.

    Results are cached for the lifetime of the process.
    """
    builtin_dir = _builtin_strategies_dir()
    result: dict[str, DiscoveryStrategy] = {}
    for name in sorted(_BUILTIN_NAMES):
        path = builtin_dir / f"{name}.yaml"
        result[name] = load_strategy_from_yaml(path)
    return result


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

    Resolution order: custom dir first (allows overrides), then builtins.

    Args:
        name: Strategy name ("disruption", "moonshot", or custom name)
        strategies_dir: Directory to search for custom strategies (optional)

    Returns:
        Strategy if found, None otherwise
    """
    # Check custom strategies dir first (user overrides take precedence)
    if strategies_dir is not None:
        yaml_path = strategies_dir / f"{name}.yaml"
        if yaml_path.exists():
            try:
                return load_strategy_from_yaml(yaml_path)
            except (ValueError, ValidationError):
                pass

        # Case-insensitive name match in custom dir
        for strategy in load_all_custom_strategies(strategies_dir):
            if strategy.name.lower() == name.lower():
                return strategy

    # Fall back to built-in strategies
    builtins = load_builtin_strategies()
    if name.lower() in builtins:
        return builtins[name.lower()]

    return None


def list_all_strategies(strategies_dir: Path | None = None) -> dict[str, list[DiscoveryStrategy]]:
    """List all available strategies (built-in + custom).

    Args:
        strategies_dir: Directory to search for custom strategies (optional)

    Returns:
        Dict with "builtin" and "custom" keys
    """
    builtins = load_builtin_strategies()
    builtin_list = list(builtins.values())
    builtin_names = {s.name for s in builtin_list}

    custom: list[DiscoveryStrategy] = []
    if strategies_dir:
        all_from_dir = load_all_custom_strategies(strategies_dir)
        # Exclude strategies that match builtin names to avoid double-listing
        custom = [s for s in all_from_dir if s.name not in builtin_names]

    return {"builtin": builtin_list, "custom": custom}


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

    result: str = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return result

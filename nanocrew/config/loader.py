"""Configuration loading utilities."""

import json
from pathlib import Path
from typing import Any

from nanocrew.config.schema import Config


def get_config_path() -> Path:
    """Get the default configuration file path."""
    return Path.home() / ".nanocrew" / "config.json"


def get_data_dir() -> Path:
    """Get the nanobot data directory."""
    from nanocrew.utils.helpers import get_data_path

    return get_data_path()


def load_config(config_path: Path | None = None) -> Config:
    """
    Load configuration from file or create default.

    Args:
        config_path: Optional path to config file. Uses default if not provided.

    Returns:
        Loaded configuration object.
    """
    path = config_path or get_config_path()

    if path.exists():
        try:
            with open(path) as f:
                data = json.load(f)
            data = _migrate_config(data)
            return Config.model_validate(convert_keys(data))
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Failed to load config from {path}: {e}")
            print("Using default configuration.")

    return Config()


def save_config(config: Config, config_path: Path | None = None) -> None:
    """
    Save configuration to file.

    Args:
        config: Configuration to save.
        config_path: Optional path to save to. Uses default if not provided.
    """
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to camelCase format
    data = config.model_dump()
    data = convert_to_camel(data)

    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _migrate_config(data: dict) -> dict:
    """Migrate old config formats to current."""
    # Move tools.exec.restrictToWorkspace → tools.restrictToWorkspace
    tools = data.get("tools", {})
    exec_cfg = tools.get("exec", {})
    if "restrictToWorkspace" in exec_cfg and "restrictToWorkspace" not in tools:
        tools["restrictToWorkspace"] = exec_cfg.pop("restrictToWorkspace")

    # Migrate agents.defaults → agents.registry.main
    agents = data.get("agents", {})
    defaults = agents.get("defaults")
    registry = agents.get("registry", {})

    if defaults is not None:
        # If main doesn't exist, create it from defaults
        if "main" not in registry:
            registry["main"] = {
                "workspace": defaults.get("workspace", "~/.nanocrew/workspaces/main"),
                "model": defaults.get("model", "anthropic/claude-opus-4-5"),
                "maxTokens": defaults.get("maxTokens", 8192),
                "temperature": defaults.get("temperature", 0.7),
                "maxToolIterations": defaults.get("maxToolIterations", 20),
                "memoryWindow": defaults.get("memoryWindow", 50),
                "systemPrompt": defaults.get("systemPrompt", ""),
            }
        # Remove defaults field
        del agents["defaults"]

    return data


def convert_keys(data: Any, is_binding_key: bool = False) -> Any:
    """Convert camelCase keys to snake_case for Pydantic.

    Args:
        data: Data to convert
        is_binding_key: If True, don't convert keys (they are session identifiers)
    """
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            # Session keys (contain ':') should not be converted
            if ":" in k:
                result[k] = convert_keys(v)
            else:
                result[camel_to_snake(k)] = convert_keys(v)
        return result
    if isinstance(data, list):
        return [convert_keys(item) for item in data]
    return data


def convert_to_camel(data: Any) -> Any:
    """Convert snake_case keys to camelCase.

    Session identifiers (keys containing ':') are preserved as-is.
    """
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            # Session keys (contain ':') should not be converted
            if ":" in k:
                result[k] = convert_to_camel(v)
            else:
                result[snake_to_camel(k)] = convert_to_camel(v)
        return result
    if isinstance(data, list):
        return [convert_to_camel(item) for item in data]
    return data


def camel_to_snake(name: str) -> str:
    """Convert camelCase to snake_case."""
    result = []
    for i, char in enumerate(name):
        if char.isupper() and i > 0:
            result.append("_")
        result.append(char.lower())
    return "".join(result)


def snake_to_camel(name: str) -> str:
    """Convert snake_case to camelCase."""
    components = name.split("_")
    return components[0] + "".join(x.title() for x in components[1:])

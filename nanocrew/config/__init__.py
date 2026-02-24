"""Configuration module for nanobot."""

from nanocrew.config.loader import load_config, get_config_path
from nanocrew.config.schema import Config

__all__ = ["Config", "load_config", "get_config_path"]

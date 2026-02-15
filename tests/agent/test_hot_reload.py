"""Tests for hot reload functionality."""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from nanobot.agent.registry import AgentRegistry
from nanobot.config.schema import AgentDefinition, AgentsConfig, Config


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def initial_config(temp_config_dir):
    """Create initial config with main agent only."""
    config = Config(
        agents=AgentsConfig(
            registry={
                "main": AgentDefinition(
                    workspace=str(temp_config_dir / "workspaces" / "main"),
                    model="anthropic/claude-sonnet-4",
                ),
            },
            bindings={},
        )
    )
    return config


def test_hot_reload_detects_config_change(temp_config_dir, initial_config):
    """Test hot reload detects config file changes."""
    config_file = temp_config_dir / "config.json"
    config_file.write_text(initial_config.model_dump_json())

    with patch("nanobot.config.loader.get_config_path") as mock_path:
        mock_path.return_value = config_file
        registry = AgentRegistry(initial_config)

        # Initially only main agent
        assert len(registry.list_agents()) == 1
        assert "main" in registry.list_agents()

        # Modify config to add new agent and binding
        new_config = json.loads(initial_config.model_dump_json())
        new_config["agents"]["registry"]["new_agent"] = {
            "workspace": str(temp_config_dir / "workspaces" / "new_agent"),
            "model": "openai/gpt-4",
        }
        new_config["agents"]["bindings"]["feishu:new_session"] = "new_agent"

        # Wait a bit to ensure mtime difference
        time.sleep(0.1)
        config_file.write_text(json.dumps(new_config))

        # Force reload check
        registry._last_mtime = 0

        # Should now have new agent
        agents = registry.list_agents()
        assert len(agents) == 2
        assert "new_agent" in agents


def test_hot_reload_new_binding(temp_config_dir, initial_config):
    """Test hot reload picks up new session bindings."""
    config_file = temp_config_dir / "config.json"
    config_file.write_text(initial_config.model_dump_json())

    with patch("nanobot.config.loader.get_config_path") as mock_path:
        mock_path.return_value = config_file
        registry = AgentRegistry(initial_config)

        # Initially unbound session
        assert registry.get_agent_name_for_session("feishu:new_group") == "main"

        # Add binding
        new_config = json.loads(initial_config.model_dump_json())
        new_config["agents"]["registry"]["backend"] = {
            "workspace": str(temp_config_dir / "workspaces" / "backend"),
            "model": "anthropic/claude-opus-4-5",
        }
        new_config["agents"]["bindings"]["feishu:new_group"] = "backend"

        time.sleep(0.1)
        config_file.write_text(json.dumps(new_config))

        # Force reload
        registry._last_mtime = 0

        # Should now resolve to backend
        assert registry.get_agent_name_for_session("feishu:new_group") == "backend"


def test_hot_reload_binding_removal(temp_config_dir, initial_config):
    """Test hot reload handles binding removal."""
    # Start with a binding
    initial_config.agents.registry["backend"] = AgentDefinition(
        workspace=str(temp_config_dir / "workspaces" / "backend"),
        model="anthropic/claude-opus-4-5",
    )
    initial_config.agents.bindings["feishu:temp_group"] = "backend"

    config_file = temp_config_dir / "config.json"
    config_file.write_text(initial_config.model_dump_json())

    with patch("nanobot.config.loader.get_config_path") as mock_path:
        mock_path.return_value = config_file
        registry = AgentRegistry(initial_config)

        assert registry.get_agent_name_for_session("feishu:temp_group") == "backend"

        # Remove binding
        new_config = json.loads(initial_config.model_dump_json())
        del new_config["agents"]["bindings"]["feishu:temp_group"]

        time.sleep(0.1)
        config_file.write_text(json.dumps(new_config))

        # Force reload
        registry._last_mtime = 0

        # Should now fallback to main
        assert registry.get_agent_name_for_session("feishu:temp_group") == "main"


def test_no_reload_when_unchanged(temp_config_dir, initial_config):
    """Test no reload when file hasn't changed - behavior test."""
    config_file = temp_config_dir / "config.json"
    config_file.write_text(initial_config.model_dump_json())

    with patch("nanobot.config.loader.get_config_path") as mock_path:
        mock_path.return_value = config_file

        registry = AgentRegistry(initial_config)

        # Get mtime after init
        first_mtime = registry._last_mtime

        # Access multiple times
        registry.list_agents()
        registry.list_agents()
        registry.list_agents()

        # mtime should not change (no reload)
        assert registry._last_mtime == first_mtime

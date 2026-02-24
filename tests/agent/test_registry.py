"""Unit tests for AgentRegistry."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from nanocrew.agent.registry import AgentRegistry
from nanocrew.config.schema import AgentDefinition, AgentsConfig, Config


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_config(temp_config_dir):
    """Create a sample config with multiple agents."""
    config = Config(
        agents=AgentsConfig(
            registry={
                "main": AgentDefinition(
                    workspace=str(temp_config_dir / "workspaces" / "main"),
                    model="anthropic/claude-sonnet-4",
                ),
                "backend": AgentDefinition(
                    workspace=str(temp_config_dir / "workspaces" / "backend"),
                    model="anthropic/claude-opus-4-5",
                    temperature=0.3,
                ),
            },
            bindings={
                "feishu:oc_abc123": "backend",
                "telegram:123456": "main",
            },
        )
    )
    return config


def test_agent_registry_initialization(temp_config_dir, sample_config):
    """Test AgentRegistry initializes correctly."""
    config_file = temp_config_dir / "config.json"
    config_file.write_text(sample_config.model_dump_json())

    with patch("nanocrew.config.loader.get_config_path") as mock_path:
        mock_path.return_value = config_file
        registry = AgentRegistry(sample_config)

        assert registry is not None
        assert "main" in registry.list_agents()
        assert "backend" in registry.list_agents()


def test_get_for_session_with_binding(temp_config_dir, sample_config):
    """Test get_for_session returns correct agent for bound session."""
    config_file = temp_config_dir / "config.json"
    config_file.write_text(sample_config.model_dump_json())

    with patch("nanocrew.config.loader.get_config_path") as mock_path:
        mock_path.return_value = config_file
        registry = AgentRegistry(sample_config)

        # Test bound session
        backend_agent = registry.get_for_session("feishu:oc_abc123")
        assert backend_agent.workspace == str(temp_config_dir / "workspaces" / "backend")
        assert backend_agent.model == "anthropic/claude-opus-4-5"


def test_get_for_session_unbound_defaults_to_main(temp_config_dir, sample_config):
    """Test unbound sessions default to main agent."""
    config_file = temp_config_dir / "config.json"
    config_file.write_text(sample_config.model_dump_json())

    with patch("nanocrew.config.loader.get_config_path") as mock_path:
        mock_path.return_value = config_file
        registry = AgentRegistry(sample_config)

        # Test unbound session
        main_agent = registry.get_for_session("feishu:unknown_session")
        assert main_agent.workspace == str(temp_config_dir / "workspaces" / "main")


def test_get_agent_name_for_session(temp_config_dir, sample_config):
    """Test get_agent_name_for_session returns correct agent name."""
    config_file = temp_config_dir / "config.json"
    config_file.write_text(sample_config.model_dump_json())

    with patch("nanocrew.config.loader.get_config_path") as mock_path:
        mock_path.return_value = config_file
        registry = AgentRegistry(sample_config)

        assert registry.get_agent_name_for_session("feishu:oc_abc123") == "backend"
        assert registry.get_agent_name_for_session("telegram:123456") == "main"
        assert registry.get_agent_name_for_session("unknown:session") == "main"


def test_get_agent_config(temp_config_dir, sample_config):
    """Test get_agent_config returns correct configuration."""
    config_file = temp_config_dir / "config.json"
    config_file.write_text(sample_config.model_dump_json())

    with patch("nanocrew.config.loader.get_config_path") as mock_path:
        mock_path.return_value = config_file
        registry = AgentRegistry(sample_config)

        backend_config = registry.get_agent_config("backend")
        assert backend_config.temperature == 0.3
        assert backend_config.model == "anthropic/claude-opus-4-5"


def test_get_agent_config_not_found_defaults_to_main(temp_config_dir, sample_config):
    """Test get_agent_config returns main agent for unknown agent."""
    config_file = temp_config_dir / "config.json"
    config_file.write_text(sample_config.model_dump_json())

    with patch("nanocrew.config.loader.get_config_path") as mock_path:
        mock_path.return_value = config_file
        registry = AgentRegistry(sample_config)

        config = registry.get_agent_config("nonexistent")
        # Should default to main agent
        assert config.workspace == str(temp_config_dir / "workspaces" / "main")


def test_list_agents(temp_config_dir, sample_config):
    """Test list_agents returns all registered agents."""
    config_file = temp_config_dir / "config.json"
    config_file.write_text(sample_config.model_dump_json())

    with patch("nanocrew.config.loader.get_config_path") as mock_path:
        mock_path.return_value = config_file
        registry = AgentRegistry(sample_config)

        agents = registry.list_agents()
        assert len(agents) == 2
        assert "main" in agents
        assert "backend" in agents
        assert agents["main"].model == "anthropic/claude-sonnet-4"


def test_hot_reload(temp_config_dir, sample_config):
    """Test config hot reload when file changes."""
    config_file = temp_config_dir / "config.json"
    config_file.write_text(sample_config.model_dump_json())

    with patch("nanocrew.config.loader.get_config_path") as mock_path:
        mock_path.return_value = config_file
        registry = AgentRegistry(sample_config)

        # Initially has 2 agents
        assert len(registry.list_agents()) == 2

        # Modify config to add new agent
        new_config = sample_config.model_dump()
        new_config["agents"]["registry"]["product"] = {
            "workspace": str(temp_config_dir / "workspaces" / "product"),
            "model": "openai/gpt-4",
        }
        config_file.write_text(json.dumps(new_config))

        # Force reload by modifying mtime check
        registry._last_mtime = 0

        # Now should have 3 agents
        assert len(registry.list_agents()) == 3
        assert "product" in registry.list_agents()


def test_get_workspace_for_session(temp_config_dir, sample_config):
    """Test get_workspace_for_session returns correct workspace path."""
    config_file = temp_config_dir / "config.json"
    config_file.write_text(sample_config.model_dump_json())

    with patch("nanocrew.config.loader.get_config_path") as mock_path:
        mock_path.return_value = config_file
        registry = AgentRegistry(sample_config)

        workspace = registry.get_workspace_for_session("feishu:oc_abc123")
        assert workspace == Path(temp_config_dir / "workspaces" / "backend")

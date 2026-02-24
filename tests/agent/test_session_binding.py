"""Integration tests for session-agent binding."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nanocrew.agent.manager import MultiAgentManager
from nanocrew.agent.registry import AgentRegistry
from nanocrew.config.loader import save_config
from nanocrew.config.schema import AgentDefinition, AgentsConfig, Config, ExecToolConfig


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for config and workspaces."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def multi_agent_config(temp_config_dir):
    """Create a multi-agent configuration."""
    config = Config(
        agents=AgentsConfig(
            registry={
                "main": AgentDefinition(
                    workspace=str(temp_config_dir / "workspaces" / "main"),
                    model="anthropic/claude-sonnet-4",
                ),
                "backend_dev": AgentDefinition(
                    workspace=str(temp_config_dir / "workspaces" / "backend_dev"),
                    model="anthropic/claude-opus-4-5",
                    temperature=0.3,
                    system_prompt="You are a backend development assistant.",
                ),
                "product_team": AgentDefinition(
                    workspace=str(temp_config_dir / "workspaces" / "product"),
                    model="openai/gpt-4",
                    temperature=0.7,
                ),
            },
            bindings={
                # Feishu groups
                "feishu:oc_backend_group": "backend_dev",
                "feishu:oc_product_group": "product_team",
                # Telegram chats
                "telegram:123456789": "backend_dev",
                # Unbound sessions will use "main"
            },
        )
    )
    return config


def test_session_binding_resolution(temp_config_dir, multi_agent_config):
    """Test session keys resolve to correct agents."""
    config_file = temp_config_dir / "config.json"
    config_file.write_text(multi_agent_config.model_dump_json())

    with patch("nanocrew.config.loader.get_config_path") as mock_path:
        mock_path.return_value = config_file
        registry = AgentRegistry(multi_agent_config)

        # Bound sessions
        assert registry.get_agent_name_for_session("feishu:oc_backend_group") == "backend_dev"
        assert registry.get_agent_name_for_session("feishu:oc_product_group") == "product_team"
        assert registry.get_agent_name_for_session("telegram:123456789") == "backend_dev"

        # Unbound sessions default to main
        assert registry.get_agent_name_for_session("feishu:unknown_group") == "main"
        assert registry.get_agent_name_for_session("telegram:999999") == "main"
        assert registry.get_agent_name_for_session("discord:channel_123") == "main"


def test_agent_config_isolation(temp_config_dir, multi_agent_config):
    """Test each agent has independent configuration."""
    config_file = temp_config_dir / "config.json"
    config_file.write_text(multi_agent_config.model_dump_json())

    with patch("nanocrew.config.loader.get_config_path") as mock_path:
        mock_path.return_value = config_file
        registry = AgentRegistry(multi_agent_config)

        backend = registry.get_agent_config("backend_dev")
        product = registry.get_agent_config("product_team")
        main = registry.get_agent_config("main")

        # Different models
        assert backend.model == "anthropic/claude-opus-4-5"
        assert product.model == "openai/gpt-4"
        assert main.model == "anthropic/claude-sonnet-4"

        # Different temperatures
        assert backend.temperature == 0.3
        assert product.temperature == 0.7

        # Different workspaces
        assert backend.workspace != product.workspace
        assert "backend_dev" in backend.workspace
        assert "product" in product.workspace


def test_end_to_end_session_routing(temp_config_dir, multi_agent_config):
    """Test end-to-end session to agent routing."""
    config_file = temp_config_dir / "config.json"
    config_file.write_text(multi_agent_config.model_dump_json())

    with patch("nanocrew.config.loader.get_config_path") as mock_path:
        mock_path.return_value = config_file

        bus = MagicMock()
        provider = MagicMock()
        provider.get_default_model.return_value = "anthropic/claude-sonnet-4"

        manager = MultiAgentManager(
            bus=bus,
            provider=provider,
            exec_config=ExecToolConfig(),
        )

        # Different sessions should get different loops
        backend_loop = manager.get_loop_for_session("feishu:oc_backend_group")
        product_loop = manager.get_loop_for_session("feishu:oc_product_group")
        main_loop = manager.get_loop_for_session("feishu:unbound_group")

        # Verify different agents are used
        assert backend_loop is not product_loop
        assert backend_loop is not main_loop
        assert product_loop is not main_loop

        # Same session should get same loop (cached)
        backend_loop_2 = manager.get_loop_for_session("feishu:oc_backend_group")
        assert backend_loop is backend_loop_2


def test_workspace_per_agent(temp_config_dir, multi_agent_config):
    """Test each agent has its own workspace."""
    config_file = temp_config_dir / "config.json"
    config_file.write_text(multi_agent_config.model_dump_json())

    with patch("nanocrew.config.loader.get_config_path") as mock_path:
        mock_path.return_value = config_file
        registry = AgentRegistry(multi_agent_config)

        # Get workspace for different sessions
        backend_ws = registry.get_workspace_for_session("feishu:oc_backend_group")
        product_ws = registry.get_workspace_for_session("feishu:oc_product_group")
        main_ws = registry.get_workspace_for_session("feishu:any_other")

        assert backend_ws != product_ws
        assert backend_ws != main_ws
        assert product_ws != main_ws

        assert "backend_dev" in str(backend_ws)
        assert "product" in str(product_ws)
        assert "main" in str(main_ws)


def test_binding_persistence(temp_config_dir, multi_agent_config):
    """Test bindings persist in config."""
    config_file = temp_config_dir / "config.json"
    config_file.write_text(multi_agent_config.model_dump_json())

    # Load config and verify bindings
    loaded_config = Config.model_validate_json(config_file.read_text())

    assert "feishu:oc_backend_group" in loaded_config.agents.bindings
    assert loaded_config.agents.bindings["feishu:oc_backend_group"] == "backend_dev"
    assert loaded_config.agents.bindings["feishu:oc_product_group"] == "product_team"

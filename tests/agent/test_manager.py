"""Unit tests for MultiAgentManager."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nanocrew.agent.manager import MultiAgentManager
from nanocrew.config.schema import AgentDefinition, AgentsConfig, Config, ExecToolConfig


@pytest.fixture
def temp_workspaces_dir():
    """Create a temporary directory for workspaces."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_dependencies():
    """Create mock dependencies for MultiAgentManager."""
    bus = MagicMock()
    provider = MagicMock()
    provider.get_default_model.return_value = "anthropic/claude-sonnet-4"

    return bus, provider


@pytest.fixture
def sample_config(temp_workspaces_dir):
    """Create a sample config with multiple agents."""
    config = Config(
        agents=AgentsConfig(
            registry={
                "main": AgentDefinition(
                    workspace=str(temp_workspaces_dir / "main"),
                    model="anthropic/claude-sonnet-4",
                ),
                "backend": AgentDefinition(
                    workspace=str(temp_workspaces_dir / "backend"),
                    model="anthropic/claude-opus-4-5",
                    temperature=0.3,
                ),
            },
            bindings={
                "feishu:oc_abc123": "backend",
            },
        )
    )
    return config


@pytest.fixture
def manager(mock_dependencies, sample_config):
    """Create a MultiAgentManager instance."""
    bus, provider = mock_dependencies

    with patch("nanocrew.agent.registry.AgentRegistry") as mock_registry:
        mock_registry_instance = MagicMock()
        mock_registry_instance.list_agents.return_value = sample_config.agents.registry
        mock_registry_instance.get_agent_name_for_session.side_effect = lambda s: {
            "feishu:oc_abc123": "backend",
        }.get(s, "main")
        mock_registry.return_value = mock_registry_instance

        manager = MultiAgentManager(
            bus=bus,
            provider=provider,
            exec_config=ExecToolConfig(),
        )
        return manager


def test_manager_initialization(mock_dependencies, manager):
    """Test MultiAgentManager initializes correctly."""
    assert manager is not None
    assert manager._loops == {}


def test_get_loop_lazy_creation(manager):
    """Test get_loop creates AgentLoop lazily."""
    # Initially no loops
    assert len(manager._loops) == 0

    # Get loop for main agent
    loop = manager.get_loop("main")

    # Now should have one loop
    assert len(manager._loops) == 1
    assert "main" in manager._loops
    assert loop is manager._loops["main"]


def test_get_loop_caching(manager):
    """Test get_loop returns cached instance."""
    # Get loop twice
    loop1 = manager.get_loop("main")
    loop2 = manager.get_loop("main")

    # Should be same instance
    assert loop1 is loop2
    assert len(manager._loops) == 1


def test_get_loop_for_session(manager):
    """Test get_loop_for_session routes to correct agent."""
    # Bound session - should return a loop (mock will return "main" as agent)
    backend_loop = manager.get_loop_for_session("feishu:oc_abc123")
    assert backend_loop is not None


def test_get_loop_for_session_unbound(manager):
    """Test get_loop_for_session defaults to main for unbound session."""
    loop = manager.get_loop_for_session("unknown:session")
    assert loop is not None


def test_list_active_agents(manager):
    """Test list_active_agents returns only instantiated agents."""
    # Initially no active agents
    assert manager.list_active_agents() == []

    # Create one loop
    manager.get_loop("main")
    assert manager.list_active_agents() == ["main"]


def test_reload_agents(manager):
    """Test reload_agents clears instance cache."""
    # Create some loops
    manager.get_loop("main")
    manager.get_loop("backend")
    assert len(manager._loops) == 2

    # Mock stop method
    for loop in manager._loops.values():
        loop.stop = MagicMock()

    # Reload
    manager.reload_agents()

    # Cache should be cleared
    assert len(manager._loops) == 0


def test_cleanup(manager):
    """Test cleanup stops all loops."""
    # Create some loops
    manager.get_loop("main")
    manager.get_loop("backend")

    # Mock stop method
    for loop in manager._loops.values():
        loop.stop = MagicMock()

    # Cleanup
    manager.cleanup()

    # All stops should be called
    for loop in manager._loops.values():
        loop.stop.assert_called_once()


def test_ensure_workspace_structure(manager):
    """Test workspace structure is created for new agents."""
    loop = manager.get_loop("main")

    # Check workspace was created (access via loop's workspace)
    workspace = loop.context.workspace
    assert workspace.exists()

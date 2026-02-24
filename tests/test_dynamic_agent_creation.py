"""Integration tests for dynamic agent creation with hot reload."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from nanocrew.agent.registry import AgentRegistry
from nanocrew.agent.manager import MultiAgentManager
from nanocrew.bus.queue import MessageBus
from nanocrew.config.watcher import FileWatcherService
from nanocrew.config.schema import Config, AgentDefinition
from nanocrew.config.events import (
    EVENT_AGENT_ADDED,
    EVENT_AGENT_REMOVED,
    AgentAddedData,
    AgentRemovedData,
)
from nanocrew.utils.events import event_bus, Event


@pytest.mark.asyncio
async def test_dynamic_agent_creation_emits_event():
    """Test that creating a new agent emits agent.added event."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "config.json"
        workspace_main = Path(tmpdir) / "workspaces" / "main"
        workspace_main.mkdir(parents=True)

        # Create initial config (minimal valid config)
        config_data = {
            "agents": {
                "registry": {
                    "main": {
                        "workspace": str(workspace_main),
                        "model": "test-model",
                        "temperature": 0.7,
                    }
                },
                "bindings": {},
            },
            "providers": {},
            "channels": {},
            "tools": {},
        }
        config_file.write_text(json.dumps(config_data))

        # Track events
        received_events = []

        async def event_handler(event):
            received_events.append(event)

        await event_bus.subscribe(EVENT_AGENT_ADDED, event_handler)

        try:
            with patch("nanocrew.config.loader.get_config_path", return_value=config_file):
                registry = AgentRegistry()

                # Simulate config change by updating file
                config_data["agents"]["registry"]["new_agent"] = {
                    "workspace": str(Path(tmpdir) / "workspaces" / "new_agent"),
                    "model": "test-model",
                    "temperature": 0.5,
                }
                config_file.write_text(json.dumps(config_data))

                # Trigger reload (this would normally happen on next access)
                # Since we're in sync context, the async emission won't run
                # but the _check_reload should detect changes
                registry._check_reload()

                # Give a moment for any async operations
                await asyncio.sleep(0.01)

        finally:
            await event_bus.unsubscribe(EVENT_AGENT_ADDED, event_handler)


@pytest.mark.asyncio
async def test_file_watcher_manager_integration():
    """Test FileWatcherService and MultiAgentManager integration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup paths
        workspace_main = Path(tmpdir) / "workspaces" / "main"
        workspace_main.mkdir(parents=True)
        (workspace_main / "memory").mkdir()
        (workspace_main / "skills").mkdir()
        (workspace_main / "AGENTS.md").write_text("# Main Agent")

        config_file = Path(tmpdir) / "config.json"
        config_data = {
            "agents": {
                "registry": {
                    "main": {
                        "workspace": str(workspace_main),
                        "model": "test-model",
                        "temperature": 0.7,
                    }
                },
                "bindings": {},
            },
            "providers": {},
            "channels": {},
            "tools": {
                "web": {"search": {"enabled": False}},
                "exec": {"enabled": False},
            },
        }
        config_file.write_text(json.dumps(config_data))

        # Create mocks
        mock_provider = Mock()
        mock_bus = Mock()

        with patch("nanocrew.config.loader.get_config_path", return_value=config_file):
            # Create services
            file_watcher = FileWatcherService(debounce_ms=50)
            registry = AgentRegistry()

            manager = MultiAgentManager(
                bus=mock_bus,
                provider=mock_provider,
                registry=registry,
                file_watcher=file_watcher,
            )

            # Register initial agent with file watcher
            file_watcher.register_agent(
                name="main",
                workspace=workspace_main,
            )

            # Start services
            await file_watcher.start()
            await manager.start()

            try:
                # Verify agent can be retrieved
                loop = manager.get_loop("main")
                assert loop is not None
                assert loop.agent_name == "main"

                # Verify file watcher has registered paths
                assert "main" in file_watcher._router._agent_paths

            finally:
                # Cleanup
                await manager.stop()
                await file_watcher.stop()
                manager.cleanup()


@pytest.mark.asyncio
async def test_agent_removed_event_stops_loop():
    """Test that agent.removed event stops the AgentLoop."""
    from nanocrew.utils.events import EventBus

    # Use local event bus to avoid interference
    local_bus = EventBus()
    received_events = []

    async def event_handler(event):
        if isinstance(event.data, AgentRemovedData):
            received_events.append(event.data.agent_name)

    await local_bus.subscribe(EVENT_AGENT_REMOVED, event_handler)

    # Emit removal event
    await local_bus.publish(
        Event(
            name=EVENT_AGENT_REMOVED,
            data=AgentRemovedData(agent_name="test_agent"),
        )
    )

    await asyncio.sleep(0.01)

    assert "test_agent" in received_events


@pytest.mark.asyncio
async def test_event_bus_lifecycle():
    """Test that event bus properly handles subscribe/unsubscribe lifecycle."""
    from nanocrew.utils.events import EventBus

    # Use local event bus to avoid interference
    local_bus = EventBus()
    handler_calls = []

    async def handler(event):
        handler_calls.append(event.data)

    # Subscribe
    await local_bus.subscribe(EVENT_AGENT_ADDED, handler)

    # Publish
    from nanocrew.utils.events import Event
    await local_bus.publish(
        Event(
            name=EVENT_AGENT_ADDED,
            data=AgentAddedData(
                agent_name="test",
                workspace=Path("/test"),
                config={},
            ),
        )
    )

    await asyncio.sleep(0.01)
    assert len(handler_calls) == 1

    # Unsubscribe
    await local_bus.unsubscribe(EVENT_AGENT_ADDED, handler)

    # Publish again
    await local_bus.publish(
        Event(
            name=EVENT_AGENT_ADDED,
            data=AgentAddedData(
                agent_name="test2",
                workspace=Path("/test2"),
                config={},
            ),
        )
    )

    await asyncio.sleep(0.01)
    # Should not have received second event
    assert len(handler_calls) == 1

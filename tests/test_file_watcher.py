"""Tests for the file watcher service."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from nanocrew.config.watcher import (
    FileWatcherService,
    AgentEventRouter,
    AgentFileEventHandler,
)
from nanocrew.utils.file_cache import FileCache
from nanocrew.config.events import AgentAddedData, EVENT_AGENT_ADDED, event_bus
from nanocrew.utils.events import Event


@pytest.mark.asyncio
async def test_agent_event_router_register():
    """Test registering an agent with the router."""
    router = AgentEventRouter()
    workspace = Path("/test/workspace")

    paths = router.register_agent("test_agent", workspace)

    # Should return 7 paths (5 bootstrap + memory + skills)
    assert len(paths) == 7
    assert any(p.name == "AGENTS.md" for p in paths)
    assert any(p.name == "skills" for p in paths)


@pytest.mark.asyncio
async def test_agent_event_router_get_affected_agents():
    """Test getting affected agents for a changed path."""
    router = AgentEventRouter()
    workspace = Path("/test/workspace")

    router.register_agent("agent1", workspace)
    router.register_agent("agent2", Path("/other/workspace"))

    # File in agent1's workspace
    changed_path = workspace / "AGENTS.md"
    affected = router.get_affected_agents(changed_path)

    assert "agent1" in affected
    assert "agent2" not in affected


@pytest.mark.asyncio
async def test_agent_event_router_skills_directory():
    """Test that skills directory changes affect the right agent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        router = AgentEventRouter()
        workspace = Path(tmpdir)

        # Create skills directory
        (workspace / "skills").mkdir()

        router.register_agent("agent1", workspace)

        # Check registered paths
        paths = router.get_paths_for_agent("agent1")
        skills_path = next(p for p in paths if p.name == "skills")
        assert skills_path.is_dir()  # Verify skills is registered as directory

        # File in skills subdirectory
        changed_path = workspace / "skills" / "github" / "SKILL.md"
        affected = router.get_affected_agents(changed_path)

        assert "agent1" in affected


@pytest.mark.asyncio
async def test_agent_event_router_unregister():
    """Test unregistering an agent."""
    router = AgentEventRouter()
    workspace = Path("/test/workspace")

    router.register_agent("test_agent", workspace)
    paths = router.unregister_agent("test_agent")

    # Should return the same paths that were registered
    assert len(paths) == 7

    # Should no longer be affected by changes
    changed_path = workspace / "AGENTS.md"
    affected = router.get_affected_agents(changed_path)
    assert "test_agent" not in affected


@pytest.mark.asyncio
async def test_file_watcher_service_lifecycle():
    """Test starting and stopping the file watcher service."""
    service = FileWatcherService(debounce_ms=100)

    # Start
    await service.start()
    assert service._observer.is_alive()

    # Stop
    await service.stop()
    assert not service._observer.is_alive()


@pytest.mark.asyncio
async def test_file_watcher_register_agent():
    """Test registering an agent for file watching."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = FileWatcherService(debounce_ms=100)
        workspace = Path(tmpdir)

        # Create necessary directories
        (workspace / "memory").mkdir()
        (workspace / "skills").mkdir()

        # Create a bootstrap file
        (workspace / "AGENTS.md").write_text("test content")

        # Register before starting (sync version)
        service.register_agent(name="test_agent", workspace=workspace)

        assert "test_agent" in service._router._agent_paths


@pytest.mark.asyncio
async def test_file_watcher_avoids_duplicate_watches():
    """Test that duplicate watches are not created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = FileWatcherService(debounce_ms=100)
        workspace = Path(tmpdir)

        (workspace / "memory").mkdir()
        (workspace / "skills").mkdir()
        (workspace / "AGENTS.md").write_text("test")

        # Start the service
        await service.start()

        # Register same agent twice
        service.register_agent(name="test_agent", workspace=workspace)
        initial_watch_count = len(service._watch_handlers)

        service.register_agent(name="test_agent", workspace=workspace)
        final_watch_count = len(service._watch_handlers)

        # Watch count should not increase
        assert final_watch_count == initial_watch_count

        await service.stop()


@pytest.mark.asyncio
async def test_file_watcher_dynamic_registration():
    """Test dynamic path registration via agent.added event."""
    with tempfile.TemporaryDirectory() as tmpdir:
        service = FileWatcherService(debounce_ms=100)
        workspace = Path(tmpdir)

        # Create workspace structure
        workspace.mkdir(exist_ok=True)
        (workspace / "memory").mkdir()
        (workspace / "skills").mkdir()
        (workspace / "AGENTS.md").write_text("test")

        await service.start()

        # Initially no agents registered
        assert len(service._router._agent_paths) == 0

        # Emit agent.added event
        await event_bus.publish(
            Event(
                name=EVENT_AGENT_ADDED,
                data=AgentAddedData(
                    agent_name="dynamic_agent",
                    workspace=workspace,
                    config={},
                ),
            )
        )

        # Wait for event processing (needs more time for file system)
        await asyncio.sleep(0.5)

        # Agent should now be registered
        assert "dynamic_agent" in service._router._agent_paths

        await service.stop()


@pytest.mark.asyncio
async def test_file_watcher_detects_file_changes():
    """Test that file changes are detected and trigger cache invalidation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = FileCache(debounce_ms=50)
        router = AgentEventRouter()
        handler = AgentFileEventHandler(cache, router)

        # Create a test file
        test_file = Path(tmpdir) / "test.txt"
        test_file.write_text("original")

        # Populate cache
        await cache.get(test_file)

        # Simulate file modification event
        from watchdog.events import FileModifiedEvent

        event = FileModifiedEvent(str(test_file))
        handler.on_modified(event)

        # Wait for debounce
        await asyncio.sleep(0.1)

        # Modify file
        test_file.write_text("modified")

        # Should get new content (cache invalidated)
        content = await cache.get(test_file)
        assert content == "modified"


@pytest.mark.asyncio
async def test_file_watcher_unsubscribe_on_stop():
    """Test that event subscription is cleaned up on stop."""
    service = FileWatcherService(debounce_ms=100)

    await service.start()

    # Handler should be subscribed
    assert service._agent_added_handler is not None

    await service.stop()

    # Handler should be cleaned up
    assert service._agent_added_handler is None

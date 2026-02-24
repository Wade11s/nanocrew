"""File watcher service with watchdog-based monitoring."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger
from watchdog.observers import Observer
from watchdog.events import (
    FileSystemEvent,
    FileSystemEventHandler,
    FileModifiedEvent,
)

from nanocrew.utils.events import Event, event_bus
from nanocrew.utils.file_cache import FileCache, CacheInvalidator
from nanocrew.config.events import EVENT_AGENT_ADDED, AgentAddedData

if TYPE_CHECKING:
    from nanocrew.agent.context import ContextBuilder
    from nanocrew.agent.skills import SkillsLoader


class AgentEventRouter:
    """Routes file system events to affected agents."""

    def __init__(self) -> None:
        """Initialize the router."""
        self._agent_paths: dict[str, list[Path]] = {}  # agent_name -> paths
        self._path_to_agents: dict[Path, set[str]] = {}  # path -> {agent_names}

    def register_agent(self, name: str, workspace: Path) -> list[Path]:
        """Register an agent and return paths to watch.

        Args:
            name: Agent name
            workspace: Agent workspace path

        Returns:
            List of paths to watch for this agent
        """
        paths = [
            workspace / "AGENTS.md",
            workspace / "SOUL.md",
            workspace / "USER.md",
            workspace / "TOOLS.md",
            workspace / "IDENTITY.md",
            workspace / "memory" / "MEMORY.md",
            workspace / "skills",
        ]

        self._agent_paths[name] = paths

        for path in paths:
            if path not in self._path_to_agents:
                self._path_to_agents[path] = set()
            self._path_to_agents[path].add(name)

        logger.debug(f"AgentEventRouter: Registered agent '{name}' with {len(paths)} paths")
        return paths

    def unregister_agent(self, name: str) -> list[Path]:
        """Unregister an agent and return previously watched paths.

        Args:
            name: Agent name

        Returns:
            List of paths that were watched for this agent
        """
        paths = self._agent_paths.pop(name, [])

        for path in paths:
            if path in self._path_to_agents:
                self._path_to_agents[path].discard(name)
                if not self._path_to_agents[path]:
                    del self._path_to_agents[path]

        logger.debug(f"AgentEventRouter: Unregistered agent '{name}'")
        return paths

    def get_affected_agents(self, changed_path: Path) -> set[str]:
        """Get agents affected by a file change.

        Args:
            changed_path: The path that changed

        Returns:
            Set of agent names affected by the change
        """
        affected: set[str] = set()

        for registered_path, agents in self._path_to_agents.items():
            if changed_path == registered_path:
                affected.update(agents)
            elif registered_path.is_dir():
                # Check if changed_path is under registered_path
                try:
                    # Use relative_to which raises ValueError if not relative
                    changed_path.relative_to(registered_path)
                    affected.update(agents)
                except ValueError:
                    pass

        return affected

    def get_paths_for_agent(self, name: str) -> list[Path]:
        """Get all watched paths for an agent.

        Args:
            name: Agent name

        Returns:
            List of paths watched for this agent
        """
        return self._agent_paths.get(name, [])


class AgentFileEventHandler(FileSystemEventHandler):
    """Handles file system events and routes to cache invalidation."""

    def __init__(
        self,
        file_cache: FileCache,
        router: AgentEventRouter,
    ) -> None:
        """Initialize the handler.

        Args:
            file_cache: The file cache to invalidate
            router: The event router for finding affected agents
        """
        self._file_cache = file_cache
        self._router = router

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events.

        Args:
            event: The file system event
        """
        if event.is_directory:
            return

        if not isinstance(event, FileModifiedEvent):
            return

        path = Path(event.src_path)
        logger.debug(f"FileWatcher: Detected modification: {path}")

        # Trigger debounced cache invalidation
        # Handle both sync and async contexts (watchdog runs in separate thread)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._file_cache.invalidate(path))
        except RuntimeError:
            # No event loop running (e.g., in tests or thread context)
            # Skip async invalidation - will be reloaded on next access
            pass

        # Notify affected agents
        affected_agents = self._router.get_affected_agents(path)
        for agent_name in affected_agents:
            logger.info(f"FileWatcher: Notifying agent '{agent_name}' of change in {path}")


class FileWatcherService:
    """Global file watcher service for monitoring agent files.

    Features:
    - Watchdog-based file monitoring
    - Dynamic path registration when agents are added
    - Debounced cache invalidation
    - Lifecycle management (start/stop)
    """

    def __init__(self, debounce_ms: int = 500) -> None:
        """Initialize the file watcher service.

        Args:
            debounce_ms: Debounce delay for cache invalidation in milliseconds
        """
        self._observer = Observer()
        self._file_cache = FileCache(debounce_ms=debounce_ms)
        self._router = AgentEventRouter()
        self._event_handler = AgentFileEventHandler(self._file_cache, self._router)

        # Track watchdog watch handlers for cleanup
        self._watch_handlers: dict[Path, Any] = {}

        # Event subscription handle
        self._agent_added_handler: Any = None

    @property
    def file_cache(self) -> FileCache:
        """Get the file cache instance."""
        return self._file_cache

    async def start(self) -> None:
        """Start the file watcher service."""
        self._observer.start()

        # Subscribe to agent added events
        self._agent_added_handler = self._on_agent_added
        await event_bus.subscribe(EVENT_AGENT_ADDED, self._agent_added_handler)

        logger.info("FileWatcherService: Started")

    async def stop(self) -> None:
        """Stop the file watcher service."""
        # Unsubscribe from events
        if self._agent_added_handler:
            await event_bus.unsubscribe(EVENT_AGENT_ADDED, self._agent_added_handler)
            self._agent_added_handler = None

        # Clear pending invalidations
        await self._file_cache.clear_pending()

        # Stop observer
        self._observer.stop()
        self._observer.join()

        logger.info("FileWatcherService: Stopped")

    async def _on_agent_added(self, event: Event[AgentAddedData]) -> None:
        """Handle agent added event.

        Args:
            event: The agent added event
        """
        data = event.data
        logger.info(f"FileWatcherService: Agent '{data.agent_name}' added, adding watches")

        # Wait for workspace to exist (brief delay for filesystem)
        workspace = data.workspace
        for _ in range(10):  # Max 1 second wait
            if workspace.exists():
                break
            await asyncio.sleep(0.1)

        if not workspace.exists():
            logger.warning(f"FileWatcherService: Workspace {workspace} not created after 1s")
            return

        # Register paths
        paths = self._router.register_agent(data.agent_name, workspace)

        # Add watches
        for path in paths:
            await self._add_watch_path(path)

        logger.info(f"FileWatcherService: Now watching agent '{data.agent_name}'")

    async def _add_watch_path(self, path: Path) -> None:
        """Add a path to watchdog monitoring.

        Args:
            path: Path to watch (file or directory)
        """
        if path in self._watch_handlers:
            return  # Already watching

        # Determine watch path and recursive flag
        if path.is_dir():
            watch_path = path
            recursive = True
        else:
            watch_path = path.parent
            recursive = False

        # Ensure directory exists
        if not watch_path.exists():
            logger.debug(f"FileWatcherService: Skipping watch for non-existent {watch_path}")
            return

        try:
            handler = self._observer.schedule(
                self._event_handler,
                str(watch_path),
                recursive=recursive,
            )
            self._watch_handlers[path] = handler
            logger.debug(f"FileWatcherService: Watching {watch_path} (recursive={recursive})")
        except Exception as e:
            logger.error(f"FileWatcherService: Failed to watch {watch_path}: {e}")

    def register_agent(
        self,
        name: str,
        workspace: Path,
        context_builder: ContextBuilder | None = None,
        skills_loader: SkillsLoader | None = None,
    ) -> None:
        """Register an agent for file watching.

        This is used for initial agents at startup. New agents created
        dynamically are handled via events.

        Args:
            name: Agent name
            workspace: Agent workspace path
            context_builder: Optional context builder to register as invalidator
            skills_loader: Optional skills loader to register as invalidator
        """
        # Register cache invalidators
        if context_builder and isinstance(context_builder, CacheInvalidator):
            self._file_cache.register_invalidator(context_builder)

        if skills_loader and isinstance(skills_loader, CacheInvalidator):
            self._file_cache.register_invalidator(skills_loader)

        # Register paths
        paths = self._router.register_agent(name, workspace)

        # Add watches (sync version for startup)
        for path in paths:
            if path in self._watch_handlers:
                continue

            if path.is_dir():
                watch_path = path
                recursive = True
            else:
                watch_path = path.parent
                recursive = False

            if not watch_path.exists():
                continue

            try:
                handler = self._observer.schedule(
                    self._event_handler,
                    str(watch_path),
                    recursive=recursive,
                )
                self._watch_handlers[path] = handler
            except Exception as e:
                logger.error(f"FileWatcherService: Failed to watch {watch_path}: {e}")

        logger.debug(f"FileWatcherService: Registered initial agent '{name}'")

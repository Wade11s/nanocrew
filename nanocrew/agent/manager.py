"""Multi-agent manager for handling multiple agent instances."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from nanocrew.agent.registry import AgentRegistry
from nanocrew.config.schema import AgentDefinition
from nanocrew.utils.events import Event, event_bus
from nanocrew.config.events import (
    EVENT_AGENT_ADDED,
    EVENT_AGENT_REMOVED,
    EVENT_AGENT_UPDATED,
    AgentAddedData,
    AgentRemovedData,
    AgentUpdatedData,
)

if TYPE_CHECKING:
    from nanocrew.agent.loop import AgentLoop
    from nanocrew.bus.queue import MessageBus
    from nanocrew.providers.base import LLMProvider
    from nanocrew.config.schema import ExecToolConfig, CronService
    from nanocrew.config.watcher import FileWatcherService


class MultiAgentManager:
    """
    Manages multiple AgentLoop instances for different agents.

    Each agent has its own:
    - AgentLoop instance
    - Workspace directory
    - Model configuration
    - Session history

    Instances are created lazily and cached for reuse.
    """

    def __init__(
        self,
        bus: "MessageBus",
        provider: "LLMProvider",
        registry: AgentRegistry | None = None,
        tavily_api_key: str | None = None,
        exec_config: "ExecToolConfig | None" = None,
        cron_service: "CronService | None" = None,
        restrict_to_workspace: bool = False,
        file_watcher: "FileWatcherService | None" = None,
    ):
        """
        Initialize the multi-agent manager.

        Args:
            bus: Message bus for communication
            provider: LLM provider for all agents
            registry: Agent registry (creates default if None)
            tavily_api_key: API key for web search
            exec_config: Shell execution configuration
            cron_service: Cron service for scheduled tasks
            restrict_to_workspace: Whether to restrict tools to workspace
            file_watcher: File watcher service for cache invalidation
        """
        self.bus = bus
        self.provider = provider
        self.registry = registry or AgentRegistry()
        self.tavily_api_key = tavily_api_key
        self.exec_config = exec_config
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace
        self._file_watcher = file_watcher

        # Cache of agent_name -> AgentLoop
        self._loops: dict[str, "AgentLoop"] = {}

        # Event handler references (for unsubscribe)
        self._on_agent_added_handler: Any = None
        self._on_agent_removed_handler: Any = None
        self._on_agent_updated_handler: Any = None

    def _create_agent_loop(self, agent_name: str, config: AgentDefinition) -> "AgentLoop":
        """
        Create a new AgentLoop for the given agent configuration.

        Args:
            agent_name: Name of the agent
            config: Agent configuration

        Returns:
            Configured AgentLoop instance
        """
        from nanocrew.agent.loop import AgentLoop
        from nanocrew.config.schema import ExecToolConfig
        from nanocrew.cron.service import CronService

        workspace = Path(config.workspace).expanduser()

        # Ensure workspace exists with full structure
        workspace.mkdir(parents=True, exist_ok=True)
        self._ensure_workspace_structure(workspace, agent_name)

        loop = AgentLoop(
            bus=self.bus,
            provider=self.provider,
            workspace=workspace,
            agent_name=agent_name,
            registry=self.registry,
            max_iterations=config.max_tool_iterations,
            memory_window=config.memory_window,
            tavily_api_key=self.tavily_api_key,
            exec_config=self.exec_config or ExecToolConfig(),
            cron_service=self.cron_service,
            restrict_to_workspace=self.restrict_to_workspace,
        )

        logger.info(f"MultiAgentManager: Created AgentLoop for '{agent_name}' at {workspace}")
        return loop

    def get_loop(self, agent_name: str) -> "AgentLoop":
        """
        Get or create an AgentLoop for the named agent.

        Args:
            agent_name: Name of the agent

        Returns:
            AgentLoop instance for the agent
        """
        # Check if we need to reload config (agent might have been added/removed)
        self.registry._check_reload()

        if agent_name not in self._loops:
            config = self.registry.get_agent_config(agent_name)
            self._loops[agent_name] = self._create_agent_loop(agent_name, config)

            # Register with file watcher if available
            if self._file_watcher:
                loop = self._loops[agent_name]
                self._file_watcher.register_agent(
                    name=agent_name,
                    workspace=Path(config.workspace).expanduser(),
                    context_builder=loop.context,
                    skills_loader=loop.context.skills,
                )

        return self._loops[agent_name]

    def get_loop_for_session(self, session_key: str) -> "AgentLoop":
        """
        Get the appropriate AgentLoop for a session.

        Args:
            session_key: Session identifier (e.g., "feishu:oc_xxx")

        Returns:
            AgentLoop instance assigned to the session
        """
        agent_name = self.registry.get_agent_name_for_session(session_key)
        logger.info(f"MultiAgentManager: Session '{session_key}' -> Agent '{agent_name}'")
        return self.get_loop(agent_name)

    def get_agent_for_session(self, session_key: str) -> AgentDefinition:
        """
        Get the agent configuration for a session.

        Args:
            session_key: Session identifier

        Returns:
            Agent configuration
        """
        return self.registry.get_for_session(session_key)

    def list_active_agents(self) -> list[str]:
        """
        List all active (instantiated) agent names.

        Returns:
            List of agent names with active AgentLoop instances
        """
        return list(self._loops.keys())

    def reload_agents(self) -> None:
        """
        Reload agent configurations and clear instance cache.

        This should be called when configuration changes significantly
        (e.g., workspace paths changed).
        """
        logger.info("MultiAgentManager: Reloading all agents")

        # Stop existing loops
        for name, loop in self._loops.items():
            logger.debug(f"MultiAgentManager: Stopping agent '{name}'")
            loop.stop()

        # Clear cache
        self._loops.clear()

        # Force registry reload
        self.registry._check_reload()

    def _ensure_workspace_structure(self, workspace: Path, agent_name: str) -> None:
        """Ensure workspace has complete directory structure and template files."""
        from nanocrew.config.migration import ensure_agent_workspace

        ensure_agent_workspace(workspace, agent_name)

    async def start(self) -> None:
        """Start the manager and subscribe to agent lifecycle events."""
        # Subscribe to agent events
        self._on_agent_added_handler = self._handle_agent_added
        self._on_agent_removed_handler = self._handle_agent_removed
        self._on_agent_updated_handler = self._handle_agent_updated

        await event_bus.subscribe(EVENT_AGENT_ADDED, self._on_agent_added_handler)
        await event_bus.subscribe(EVENT_AGENT_REMOVED, self._on_agent_removed_handler)
        await event_bus.subscribe(EVENT_AGENT_UPDATED, self._on_agent_updated_handler)

        logger.info("MultiAgentManager: Started, subscribed to agent events")

    async def stop(self) -> None:
        """Stop the manager and unsubscribe from events."""
        # Unsubscribe from events
        if self._on_agent_added_handler:
            await event_bus.unsubscribe(EVENT_AGENT_ADDED, self._on_agent_added_handler)
            self._on_agent_added_handler = None

        if self._on_agent_removed_handler:
            await event_bus.unsubscribe(EVENT_AGENT_REMOVED, self._on_agent_removed_handler)
            self._on_agent_removed_handler = None

        if self._on_agent_updated_handler:
            await event_bus.unsubscribe(EVENT_AGENT_UPDATED, self._on_agent_updated_handler)
            self._on_agent_updated_handler = None

        logger.info("MultiAgentManager: Stopped, unsubscribed from events")

    async def _handle_agent_added(self, event: Event[AgentAddedData]) -> None:
        """Handle agent added event by pre-creating AgentLoop.

        Args:
            event: The agent added event
        """
        data = event.data
        agent_name = data.agent_name

        logger.info(f"MultiAgentManager: Agent '{agent_name}' added via event")

        # Pre-create AgentLoop if not already exists
        if agent_name not in self._loops:
            try:
                config = self.registry.get_agent_config(agent_name)
                loop = self._create_agent_loop(agent_name, config)
                self._loops[agent_name] = loop

                # Register with file watcher if available
                if self._file_watcher:
                    self._file_watcher.register_agent(
                        name=agent_name,
                        workspace=Path(config.workspace).expanduser(),
                        context_builder=loop.context,
                        skills_loader=loop.context.skills,
                    )

                logger.info(f"MultiAgentManager: Pre-created AgentLoop for '{agent_name}'")
            except Exception as e:
                logger.error(f"MultiAgentManager: Failed to pre-create agent '{agent_name}': {e}")

    async def _handle_agent_removed(self, event: Event[AgentRemovedData]) -> None:
        """Handle agent removed event by stopping and cleaning up AgentLoop.

        Args:
            event: The agent removed event
        """
        data = event.data
        agent_name = data.agent_name

        logger.info(f"MultiAgentManager: Agent '{agent_name}' removed via event")

        if agent_name in self._loops:
            try:
                loop = self._loops.pop(agent_name)
                loop.stop()
                logger.info(f"MultiAgentManager: Stopped AgentLoop for '{agent_name}'")
            except Exception as e:
                logger.error(f"MultiAgentManager: Error stopping agent '{agent_name}': {e}")

    async def _handle_agent_updated(self, event: Event[AgentUpdatedData]) -> None:
        """Handle agent updated event.

        The actual config refresh happens lazily on next use via
        registry.get_agent_config() which always calls _check_reload().

        Args:
            event: The agent updated event
        """
        data = event.data
        logger.info(
            f"MultiAgentManager: Agent '{data.agent_name}' updated: {data.changed_fields}"
        )
        # Config will be refreshed on next get_agent_config() call

    def cleanup(self) -> None:
        """Stop all agent loops and cleanup resources."""
        logger.info("MultiAgentManager: Cleaning up")
        for name, loop in self._loops.items():
            try:
                loop.stop()
            except Exception as e:
                logger.warning(f"MultiAgentManager: Error stopping '{name}': {e}")
        self._loops.clear()

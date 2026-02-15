"""Multi-agent manager for handling multiple agent instances."""

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from nanobot.agent.registry import AgentRegistry
from nanobot.config.schema import AgentDefinition

if TYPE_CHECKING:
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus
    from nanobot.providers.base import LLMProvider
    from nanobot.config.schema import ExecToolConfig, CronService


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
        brave_api_key: str | None = None,
        exec_config: "ExecToolConfig | None" = None,
        cron_service: "CronService | None" = None,
        restrict_to_workspace: bool = False,
    ):
        """
        Initialize the multi-agent manager.

        Args:
            bus: Message bus for communication
            provider: LLM provider for all agents
            registry: Agent registry (creates default if None)
            brave_api_key: API key for web search
            exec_config: Shell execution configuration
            cron_service: Cron service for scheduled tasks
            restrict_to_workspace: Whether to restrict tools to workspace
        """
        self.bus = bus
        self.provider = provider
        self.registry = registry or AgentRegistry()
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace

        # Cache of agent_name -> AgentLoop
        self._loops: dict[str, "AgentLoop"] = {}

    def _create_agent_loop(self, agent_name: str, config: AgentDefinition) -> "AgentLoop":
        """
        Create a new AgentLoop for the given agent configuration.

        Args:
            agent_name: Name of the agent
            config: Agent configuration

        Returns:
            Configured AgentLoop instance
        """
        from nanobot.agent.loop import AgentLoop
        from nanobot.config.schema import ExecToolConfig
        from nanobot.cron.service import CronService

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
            brave_api_key=self.brave_api_key,
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
        from nanobot.config.migration import ensure_agent_workspace
        ensure_agent_workspace(workspace, agent_name)

    def cleanup(self) -> None:
        """Stop all agent loops and cleanup resources."""
        logger.info("MultiAgentManager: Cleaning up")
        for name, loop in self._loops.items():
            try:
                loop.stop()
            except Exception as e:
                logger.warning(f"MultiAgentManager: Error stopping '{name}': {e}")
        self._loops.clear()

"""Agent registry for multi-agent system with hot reload support."""

import asyncio
from pathlib import Path
from typing import Any

from loguru import logger

from nanocrew.config.schema import AgentDefinition, Config
from nanocrew.config.loader import load_config, get_config_path
from nanocrew.config.events import (
    publish_agent_added,
    publish_agent_removed,
    publish_agent_updated,
)


class AgentRegistry:
    """
    Registry for managing multiple agent configurations.

    Supports hot reload of agent configurations and bindings.
    Each session can be bound to a specific agent via the bindings configuration.

    Emits events when agents are added, removed, or updated.
    """

    def __init__(self, config: Config | None = None):
        """
        Initialize the agent registry.

        Args:
            config: Initial configuration. If None, loads from disk.
        """
        self._config = config or load_config()
        self._config_path = get_config_path()
        self._last_mtime: float = 0
        self._last_agents: set[str] = set(self._config.agents.registry.keys())
        self._check_reload()

    def _get_config_mtime(self) -> float:
        """Get the modification time of the config file."""
        try:
            return self._config_path.stat().st_mtime
        except (OSError, FileNotFoundError):
            return 0

    def _check_reload(self) -> bool:
        """
        Check if config has been modified and reload if necessary.

        Emits events for agent additions, removals, and updates.

        Returns:
            True if reloaded, False otherwise.
        """
        current_mtime = self._get_config_mtime()
        if current_mtime <= self._last_mtime:
            return False

        try:
            new_config = load_config()
            old_agents = self._last_agents
            new_agents = set(new_config.agents.registry.keys())

            # Detect changes
            added = new_agents - old_agents
            removed = old_agents - new_agents
            updated = self._detect_updates(new_config, old_agents & new_agents)

            # Update state
            self._config = new_config
            self._last_mtime = current_mtime
            self._last_agents = new_agents

            # Emit events asynchronously (don't block)
            # Handle both async and sync contexts
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._emit_changes(added, removed, updated, new_config)
                )
            except RuntimeError:
                # No event loop running (e.g., in tests or CLI)
                # Events will be picked up on next async gateway cycle
                pass

            logger.debug(f"AgentRegistry: Reloaded config (mtime={current_mtime})")
            return True

        except Exception as e:
            logger.error(f"AgentRegistry: Failed to reload config: {e}")
            return False

    def _detect_updates(
        self, new_config: Config, common_agents: set[str]
    ) -> dict[str, list[str]]:
        """Detect which agents have updated configuration.

        Args:
            new_config: The newly loaded configuration
            common_agents: Set of agent names present in both old and new config

        Returns:
            Dictionary mapping agent names to lists of changed field names
        """
        updated: dict[str, list[str]] = {}

        for name in common_agents:
            old_def = self._config.agents.registry[name]
            new_def = new_config.agents.registry[name]

            changed = []
            fields_to_check = [
                "workspace",
                "model",
                "temperature",
                "max_tokens",
                "max_tool_iterations",
                "memory_window",
                "system_prompt",
            ]

            for field in fields_to_check:
                if getattr(old_def, field) != getattr(new_def, field):
                    changed.append(field)

            if changed:
                updated[name] = changed

        return updated

    async def _emit_changes(
        self,
        added: set[str],
        removed: set[str],
        updated: dict[str, list[str]],
        config: Config,
    ) -> None:
        """Emit events for configuration changes.

        Args:
            added: Set of newly added agent names
            removed: Set of removed agent names
            updated: Dictionary of updated agents and their changed fields
            config: The new configuration
        """
        # Emit added events
        for name in added:
            agent_def = config.agents.registry[name]
            await publish_agent_added(
                name=name,
                workspace=Path(agent_def.workspace).expanduser(),
                config=agent_def.model_dump(),
            )
            logger.info(f"AgentRegistry: Agent '{name}' added, event emitted")

        # Emit removed events
        for name in removed:
            await publish_agent_removed(name=name)
            logger.info(f"AgentRegistry: Agent '{name}' removed, event emitted")

        # Emit updated events
        for name, fields in updated.items():
            await publish_agent_updated(name=name, changed_fields=fields)
            logger.info(f"AgentRegistry: Agent '{name}' updated ({fields}), event emitted")

    def get_agent_config(self, name: str) -> AgentDefinition:
        """
        Get configuration for a specific agent by name.

        Args:
            name: The agent name.

        Returns:
            AgentDefinition for the named agent, or main agent as fallback.
        """
        self._check_reload()
        return self._config.agents.get_agent(name)

    def get_for_session(self, session_key: str) -> AgentDefinition:
        """
        Get agent configuration for a specific session.

        Args:
            session_key: The session identifier (e.g., "feishu:oc_xxx").

        Returns:
            AgentDefinition for the session's assigned agent.
        """
        self._check_reload()
        return self._config.agents.get_agent_for_session(session_key)

    def get_agent_name_for_session(self, session_key: str) -> str:
        """
        Get the agent name assigned to a session.

        Args:
            session_key: The session identifier.

        Returns:
            The agent name, or "main" if not bound.
        """
        self._check_reload()
        agent_name = self._config.agents.bindings.get(session_key)
        if agent_name:
            logger.debug(f"AgentRegistry: Session '{session_key}' bound to agent '{agent_name}'")
            return agent_name
        logger.debug(f"AgentRegistry: Session '{session_key}' using default agent 'main'")
        return "main"

    def list_agents(self) -> dict[str, AgentDefinition]:
        """
        List all registered agents.

        Returns:
            Dictionary mapping agent names to their configurations.
        """
        self._check_reload()
        return dict(self._config.agents.registry)

    def list_bindings(self) -> dict[str, str]:
        """
        List all session-agent bindings.

        Returns:
            Dictionary mapping session keys to agent names.
        """
        self._check_reload()
        return dict(self._config.agents.bindings)

    def get_workspace_for_session(self, session_key: str) -> Path:
        """
        Get the workspace path for a session.

        Args:
            session_key: The session identifier.

        Returns:
            Path to the session's agent workspace.
        """
        agent = self.get_for_session(session_key)
        return Path(agent.workspace).expanduser()

    @property
    def config(self) -> Config:
        """Get the current configuration (triggers reload check)."""
        self._check_reload()
        return self._config

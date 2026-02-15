"""Agent registry for multi-agent system with hot reload support."""

import os
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.config.schema import AgentDefinition, Config
from nanobot.config.loader import load_config, get_config_path


class AgentRegistry:
    """
    Registry for managing multiple agent configurations.

    Supports hot reload of agent configurations and bindings.
    Each session can be bound to a specific agent via the bindings configuration.
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

        Returns:
            True if reloaded, False otherwise.
        """
        current_mtime = self._get_config_mtime()
        if current_mtime > self._last_mtime:
            try:
                self._config = load_config()
                self._last_mtime = current_mtime
                logger.debug(f"AgentRegistry: Reloaded config (mtime={current_mtime})")
                return True
            except Exception as e:
                logger.error(f"AgentRegistry: Failed to reload config: {e}")
        return False

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

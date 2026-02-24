"""Event definitions for configuration and agent lifecycle events."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nanocrew.utils.events import Event, event_bus


@dataclass
class AgentAddedData:
    """Data for agent added event."""

    agent_name: str
    workspace: Path
    config: dict[str, Any]


@dataclass
class AgentRemovedData:
    """Data for agent removed event."""

    agent_name: str


@dataclass
class AgentUpdatedData:
    """Data for agent updated event."""

    agent_name: str
    changed_fields: list[str]


# Event name constants
EVENT_AGENT_ADDED = "agent.added"
EVENT_AGENT_REMOVED = "agent.removed"
EVENT_AGENT_UPDATED = "agent.updated"
EVENT_FILE_CHANGED = "file.changed"


async def publish_agent_added(name: str, workspace: Path, config: dict[str, Any]) -> None:
    """Publish agent added event.

    Args:
        name: Name of the new agent
        workspace: Path to the agent's workspace
        config: Agent configuration dictionary
    """
    await event_bus.publish(
        Event(name=EVENT_AGENT_ADDED, data=AgentAddedData(name, workspace, config))
    )


async def publish_agent_removed(name: str) -> None:
    """Publish agent removed event.

    Args:
        name: Name of the removed agent
    """
    await event_bus.publish(Event(name=EVENT_AGENT_REMOVED, data=AgentRemovedData(name)))


async def publish_agent_updated(name: str, changed_fields: list[str]) -> None:
    """Publish agent updated event.

    Args:
        name: Name of the updated agent
        changed_fields: List of field names that changed
    """
    await event_bus.publish(
        Event(name=EVENT_AGENT_UPDATED, data=AgentUpdatedData(name, changed_fields))
    )

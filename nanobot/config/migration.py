"""Workspace utilities for multi-agent system."""

from pathlib import Path

from loguru import logger


def ensure_agent_workspace(workspace: Path, agent_name: str) -> None:
    """
    Ensure agent workspace has complete directory structure and template files.

    Creates standard directories and template files if they don't exist.
    This is used when creating new agents via CLI or MultiAgentManager.

    Args:
        workspace: Path to agent workspace
        agent_name: Name of the agent
    """
    # Check if workspace already has structure
    if (workspace / "AGENTS.md").exists():
        logger.debug(f"Workspace structure already exists at {workspace}")
        return

    logger.info(f"Creating workspace structure for agent '{agent_name}' at {workspace}")

    # Create standard directories
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "memory").mkdir(exist_ok=True)
    (workspace / "skills").mkdir(exist_ok=True)

    # Create template files
    templates = {
        "AGENTS.md": f"""# Agent Instructions

You are a helpful AI assistant. Be concise, accurate, and friendly.

## Guidelines

- Always explain what you're doing before taking actions
- Ask for clarification when the request is ambiguous
- Use tools to help accomplish tasks
- Remember important information in memory/MEMORY.md; past events are logged in memory/HISTORY.md

## Multi-Agent System

This is agent `{agent_name}` with its own isolated workspace.

When users ask you to create other agents, use the CLI commands:
- `nanobot agent create <name>` - create a new agent
- `nanobot agent bind <session> <agent>` - bind a session to an agent
""",
        "SOUL.md": f"""# Soul

I am {agent_name}, a lightweight AI assistant.

## Personality

- Helpful and friendly
- Concise and to the point
- Curious and eager to learn

## Values

- Accuracy over speed
- User privacy and safety
- Transparency in actions
""",
        "USER.md": """# User

Information about the user goes here.

## Preferences

- Communication style: (casual/formal)
- Timezone: (your timezone)
- Language: (your preferred language)
""",
    }

    for filename, content in templates.items():
        file_path = workspace / filename
        if not file_path.exists():
            file_path.write_text(content)
            logger.debug(f"Created {filename} for agent '{agent_name}'")

    # Create memory files
    memory_dir = workspace / "memory"
    memory_file = memory_dir / "MEMORY.md"
    if not memory_file.exists():
        memory_file.write_text("""# Long-term Memory

This file stores important information that should persist across sessions.

## User Information

(Important facts about the user)

## Preferences

(User preferences learned over time)

## Important Notes

(Things to remember)
""")
        logger.debug(f"Created memory/MEMORY.md for agent '{agent_name}'")

    history_file = memory_dir / "HISTORY.md"
    if not history_file.exists():
        history_file.write_text("")
        logger.debug(f"Created memory/HISTORY.md for agent '{agent_name}'")


def _get_data_dir() -> Path:
    """Get nanocrew data directory."""
    return Path.home() / ".nanocrew"


def ensure_workspaces_structure() -> Path:
    """
    Ensure workspaces directory structure exists.

    Creates ~/.nanocrew/workspaces/main/ if it doesn't exist.

    Returns:
        Path to main workspace.
    """
    main = _get_data_dir() / "workspaces" / "main"
    main.mkdir(parents=True, exist_ok=True)

    # Create standard subdirectories
    (main / ".sessions").mkdir(exist_ok=True)
    (main / "memory").mkdir(exist_ok=True)
    (main / "skills").mkdir(exist_ok=True)

    return main


def get_main_workspace() -> Path:
    """Get the main workspace path, creating if necessary."""
    main = _get_data_dir() / "workspaces" / "main"
    if not main.exists():
        return ensure_workspaces_structure()
    return main

"""CLI commands for nanocrew."""

import asyncio
import os
import signal
from pathlib import Path
import select
import sys

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout

from nanocrew import __version__, __logo__

app = typer.Typer(
    name="nanocrew",
    help=f"{__logo__} nanocrew - Multi-Agent AI Assistant",
    no_args_is_help=True,
)

console = Console()
EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}

# ---------------------------------------------------------------------------
# CLI input: prompt_toolkit for editing, paste, history, and display
# ---------------------------------------------------------------------------

_PROMPT_SESSION: PromptSession | None = None
_SAVED_TERM_ATTRS = None  # original termios settings, restored on exit


def _flush_pending_tty_input() -> None:
    """Drop unread keypresses typed while the model was generating output."""
    try:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return
    except Exception:
        return

    try:
        import termios

        termios.tcflush(fd, termios.TCIFLUSH)
        return
    except Exception:
        pass

    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            if not os.read(fd, 4096):
                break
    except Exception:
        return


def _restore_terminal() -> None:
    """Restore terminal to its original state (echo, line buffering, etc.)."""
    if _SAVED_TERM_ATTRS is None:
        return
    try:
        import termios

        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _SAVED_TERM_ATTRS)
    except Exception:
        pass


def _init_prompt_session() -> None:
    """Create the prompt_toolkit session with persistent file history."""
    global _PROMPT_SESSION, _SAVED_TERM_ATTRS

    # Save terminal state so we can restore it on exit
    try:
        import termios

        _SAVED_TERM_ATTRS = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        pass

    history_file = Path.home() / ".nanocrew" / "history" / "cli_history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    _PROMPT_SESSION = PromptSession(
        history=FileHistory(str(history_file)),
        enable_open_in_editor=False,
        multiline=False,  # Enter submits (single line mode)
    )


def _print_agent_response(response: str, render_markdown: bool) -> None:
    """Render assistant response with consistent terminal styling."""
    content = response or ""
    body = Markdown(content) if render_markdown else Text(content)
    console.print()
    console.print(f"[cyan]{__logo__} nanocrew[/cyan]")
    console.print(body)
    console.print()


def _is_exit_command(command: str) -> bool:
    """Return True when input should end interactive chat."""
    return command.lower() in EXIT_COMMANDS


async def _read_interactive_input_async() -> str:
    """Read user input using prompt_toolkit (handles paste, history, display).

    prompt_toolkit natively handles:
    - Multiline paste (bracketed paste mode)
    - History navigation (up/down arrows)
    - Clean display (no ghost characters or artifacts)
    """
    if _PROMPT_SESSION is None:
        raise RuntimeError("Call _init_prompt_session() first")
    try:
        with patch_stdout():
            return await _PROMPT_SESSION.prompt_async(
                HTML("<b fg='ansiblue'>You:</b> "),
            )
    except EOFError as exc:
        raise KeyboardInterrupt from exc


def version_callback(value: bool):
    if value:
        console.print(f"{__logo__} nanocrew v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(None, "--version", "-v", callback=version_callback, is_eager=True),
):
    """nanocrew - Personal AI Assistant."""
    pass


# ============================================================================
# Onboard / Setup
# ============================================================================


@app.command()
def onboard():
    """Initialize nanocrew configuration and workspace."""
    from nanocrew.config.loader import get_config_path, load_config, save_config
    from nanocrew.config.migration import ensure_agent_workspace
    from nanocrew.config.schema import Config
    from nanocrew.utils.helpers import get_workspace_path

    config_path = get_config_path()

    # Create or refresh config
    if config_path.exists():
        console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
        console.print("  [bold]y[/bold] = overwrite with defaults (existing values will be lost)")
        console.print(
            "  [bold]N[/bold] = refresh config, keeping existing values and adding new fields"
        )
        if typer.confirm("Overwrite?"):
            config = Config()
            save_config(config)
            console.print(f"[green]✓[/green] Config reset to defaults at {config_path}")
        else:
            config = load_config()
            save_config(config)
            console.print(
                f"[green]✓[/green] Config refreshed at {config_path} (existing values preserved)"
            )
    else:
        config = Config()
        # Ensure main agent exists
        config.agents.get_main_agent()
        save_config(config)
        console.print(f"[green]✓[/green] Created config at {config_path}")

    # Create main workspace with complete structure
    workspace = get_workspace_path()
    ensure_agent_workspace(workspace, agent_name="main")
    console.print(f"[green]✓[/green] Created main workspace at {workspace}")

    console.print(f"\n{__logo__} nanocrew is ready!")
    console.print("\n[bold]Multi-Agent System:[/bold]")
    console.print(
        "  • Default agent: [cyan]main[/cyan] at [cyan]~/.nanocrew/workspaces/main/[/cyan]"
    )
    console.print("  • Create new agents: [cyan]nanocrew agent create <name>[/cyan]")
    console.print("  • Bind sessions: [cyan]nanocrew agent bind <session> <agent>[/cyan]")
    console.print("\nNext steps:")
    console.print("  1. Add your API key to [cyan]~/.nanocrew/config.json[/cyan]")
    console.print("     Get one at: https://openrouter.ai/keys")
    console.print('  2. Chat: [cyan]nanocrew agent -m "Hello!"[/cyan]')
    console.print("\n[dim]Want Telegram? See: https://github.com/HKUDS/nanocrew#-chat-apps[/dim]")


def _create_workspace_templates(workspace: Path):
    """Create default workspace template files."""
    templates = {
        "AGENTS.md": """# Agent Instructions

You are a helpful AI assistant. Be concise, accurate, and friendly.

## Guidelines

- Always explain what you're doing before taking actions
- Ask for clarification when the request is ambiguous
- Use tools to help accomplish tasks
- Remember important information in memory/MEMORY.md; past events are logged in memory/HISTORY.md

## Multi-Agent System

This workspace supports multiple agents. Each agent has its own workspace, model configuration, and can be bound to specific chat sessions.

### Creating a New Agent

When asked to create a dedicated agent for a chat group or purpose:

1. **Choose an appropriate name**: Use lowercase letters, numbers, and underscores. Good examples:
   - `backend_dev` - for backend development discussions
   - `product_team` - for product management discussions
   - `research_agent` - for research tasks

2. **Use the CLI command**:
   ```bash
   nanocrew agent create <name> --workspace "~/.nanocrew/workspaces/<name>" --model "<model>"
   ```

3. **Recommended models**:
   - `anthropic/claude-opus-4-5` - for complex reasoning
   - `anthropic/claude-sonnet-4` - for general tasks (faster)
   - `openai/gpt-4` - for writing tasks

### Binding an Agent to a Session

After creating an agent, bind it to a specific chat session:

```bash
nanocrew agent bind <session_key> <agent_name>
```

**Session key format**:
- Feishu: `feishu:<chat_id>` (e.g., `feishu:oc_d5b928767f21d232afd24dc720890e78`)
- Telegram: `telegram:<chat_id>`
- Discord: `discord:<channel_id>`

### Example: Creating a Dedicated Agent

If a user says "Create an agent for the backend team in this Feishu group":

1. Get the Chat ID from the user's message metadata
2. Create the agent: `nanocrew agent create backend_dev --temperature 0.3`
3. Bind it: `nanocrew agent bind feishu:<chat_id> backend_dev`
4. Copy relevant config files (like API keys) to the new workspace if needed

### Viewing All Agents

```bash
nanocrew agent list
```

This shows all agents and their bindings.
""",
        "MULTI_AGENT_GUIDE.md": """# Multi-Agent System Guide

This file provides detailed guidance on the multi-agent system.

## Overview

- **Main Agent** (`main`): The default agent used when no specific binding exists
- **Custom Agents**: Created for specific purposes or teams
- **Workspace Structure**: Each agent has its own workspace at `~/.nanocrew/workspaces/<agent_name>/`

## When to Create a New Agent

Create a new agent when:
- A chat group needs a specialized system prompt
- Different teams need isolated workspaces
- You want to use different models for different purposes
- You need to separate memory/context between different use cases

## Agent Configuration

Each agent can have its own:
- **Model**: Different LLM for different capabilities
- **Temperature**: 0.3 for coding, 0.7 for creative tasks
- **System Prompt**: Custom behavior via AGENTS.md in its workspace
- **Skills**: Agent-specific skills in its workspace/skills/ directory

## CLI Commands Reference

```bash
# List all agents and bindings
nanocrew agent list

# Show agent details
nanocrew agent show <name>

# Create a new agent
nanocrew agent create <name> [--workspace <path>] [--model <model>] [--temperature <temp>]

# Bind a session to an agent
nanocrew agent bind <session_key> <agent_name>

# Unbind a session
nanocrew agent unbind <session_key>
```

## Hot Reload

Configuration changes take effect within 5 seconds without restarting the gateway.
""",
        "SOUL.md": """# Soul

I am nanocrew, a lightweight AI assistant.

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
            console.print(f"  [dim]Created {filename}[/dim]")

    # Create memory directory and MEMORY.md
    memory_dir = workspace / "memory"
    memory_dir.mkdir(exist_ok=True)
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
        console.print("  [dim]Created memory/MEMORY.md[/dim]")

    history_file = memory_dir / "HISTORY.md"
    if not history_file.exists():
        history_file.write_text("")
        console.print("  [dim]Created memory/HISTORY.md[/dim]")

    # Create skills directory for custom user skills
    skills_dir = workspace / "skills"
    skills_dir.mkdir(exist_ok=True)


def _make_provider(config):
    """Create LiteLLMProvider from config. Exits if no API key found."""
    from nanocrew.providers.litellm_provider import LiteLLMProvider

    p = config.get_provider()
    model = config.agents.get_main_agent().model
    if not (p and p.api_key) and not model.startswith("bedrock/"):
        console.print("[red]Error: No API key configured.[/red]")
        console.print("Set one in ~/.nanocrew/config.json under providers section")
        raise typer.Exit(1)
    return LiteLLMProvider(
        api_key=p.api_key if p else None,
        api_base=config.get_api_base(),
        default_model=model,
        extra_headers=p.extra_headers if p else None,
        provider_name=config.get_provider_name(),
    )


# ============================================================================
# Gateway / Server
# ============================================================================


@app.command()
def gateway(
    port: int = typer.Option(18790, "--port", "-p", help="Gateway port"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Start the nanocrew gateway."""
    from pathlib import Path
    from nanocrew.config.loader import load_config, get_data_dir
    from nanocrew.bus.queue import MessageBus
    from nanocrew.agent.registry import AgentRegistry
    from nanocrew.agent.manager import MultiAgentManager
    from nanocrew.channels.manager import ChannelManager
    from nanocrew.cron.service import CronService
    from nanocrew.cron.types import CronJob
    from nanocrew.heartbeat.service import HeartbeatService
    from nanocrew.config.watcher import FileWatcherService
    from loguru import logger

    if verbose:
        import logging

        logging.basicConfig(level=logging.DEBUG)

    console.print(f"{__logo__} Starting nanocrew gateway on port {port}...")

    config = load_config()
    bus = MessageBus()
    provider = _make_provider(config)

    # Create agent registry with hot reload support
    agent_registry = AgentRegistry(config)

    # Create file watcher service for hot reload
    file_watcher = FileWatcherService(debounce_ms=500)

    # Create multi-agent manager with file watcher
    agent_manager = MultiAgentManager(
        bus=bus,
        provider=provider,
        registry=agent_registry,
        tavily_api_key=config.tools.web.search.api_key or None,
        exec_config=config.tools.exec,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        file_watcher=file_watcher,
    )

    # Create cron service
    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    # Set cron callback - routes to the job's specified agent
    async def on_cron_job(job: CronJob) -> str | None:
        """Execute a cron job through the appropriate agent."""
        # Get agent from job payload, fallback to "main"
        agent_name = job.payload.agent or "main"

        # Validate agent exists, fallback to main with warning if not
        if agent_name not in agent_manager.registry._config.agents.registry:
            if agent_name != "main":
                logger.warning(
                    f"Cron job '{job.name}' specifies unknown agent '{agent_name}', falling back to 'main'"
                )
            agent_name = "main"

        agent_loop = agent_manager.get_loop(agent_name)
        response = await agent_loop.process_direct(
            job.payload.message,
            session_key=f"cron:{job.id}",
            channel=job.payload.channel or "cli",
            chat_id=job.payload.to or "direct",
        )
        if job.payload.deliver and job.payload.to:
            from nanocrew.bus.events import OutboundMessage

            await bus.publish_outbound(
                OutboundMessage(
                    channel=job.payload.channel or "cli",
                    chat_id=job.payload.to,
                    content=response or "",
                )
            )
        return response

    cron.on_job = on_cron_job

    # Create heartbeat service - uses main agent
    async def on_heartbeat(prompt: str) -> str:
        """Execute heartbeat through the main agent."""
        main_loop = agent_manager.get_loop("main")
        return await main_loop.process_direct(prompt, session_key="heartbeat")

    heartbeat = HeartbeatService(
        workspace=agent_registry.get_workspace_for_session("heartbeat"),
        on_heartbeat=on_heartbeat,
        interval_s=30 * 60,  # 30 minutes
        enabled=True,
    )

    # Create channel manager with multi-agent support
    channels = ChannelManager(config, bus, agent_manager)

    if channels.enabled_channels:
        console.print(f"[green]✓[/green] Channels enabled: {', '.join(channels.enabled_channels)}")
    else:
        console.print("[yellow]Warning: No channels enabled[/yellow]")

    # Register initial agents with file watcher before starting services
    for agent_name, agent_config in agent_registry.list_agents().items():
        workspace = Path(agent_config.workspace).expanduser()
        # Don't create loops yet, just register paths for watching
        # The actual loops will be created on first use
        file_watcher.register_agent(name=agent_name, workspace=workspace)

    # Show registered agents
    agents = agent_registry.list_agents()
    if agents:
        console.print(f"[green]✓[/green] Agents: {', '.join(agents.keys())}")

    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        console.print(f"[green]✓[/green] Cron: {cron_status['jobs']} scheduled jobs")

    console.print(f"[green]✓[/green] Heartbeat: every 30m")

    async def run():
        try:
            # Start file watcher first (before manager subscribes to events)
            await file_watcher.start()
            # Start agent manager (subscribes to events)
            await agent_manager.start()
            await cron.start()
            await heartbeat.start()
            # Run channel manager (which routes to appropriate agents)
            await channels.start_all()
        except KeyboardInterrupt:
            console.print("\nShutting down...")
            heartbeat.stop()
            cron.stop()
            # Stop in reverse order of startup
            await agent_manager.stop()
            await file_watcher.stop()
            agent_manager.cleanup()
            await channels.stop_all()

    asyncio.run(run())


# ============================================================================
# Agent Commands
# ============================================================================


@app.command()
def agent(
    message: str = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
    session_id: str = typer.Option("cli:direct", "--session", "-s", help="Session ID"),
    markdown: bool = typer.Option(
        True, "--markdown/--no-markdown", help="Render assistant output as Markdown"
    ),
    logs: bool = typer.Option(
        False, "--logs/--no-logs", help="Show nanocrew runtime logs during chat"
    ),
):
    """Interact with the agent directly."""
    from nanocrew.config.loader import load_config
    from nanocrew.bus.queue import MessageBus
    from nanocrew.agent.loop import AgentLoop
    from nanocrew.agent.registry import AgentRegistry
    from loguru import logger

    config = load_config()

    bus = MessageBus()
    provider = _make_provider(config)

    if logs:
        logger.enable("nanocrew")
    else:
        logger.disable("nanocrew")

    # Create registry for dynamic config fetching
    agent_registry = AgentRegistry(config)

    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        agent_name="main",
        registry=agent_registry,
        max_iterations=config.agents.get_main_agent().max_tool_iterations,
        memory_window=config.agents.get_main_agent().memory_window,
        tavily_api_key=config.tools.web.search.api_key or None,
        exec_config=config.tools.exec,
        restrict_to_workspace=config.tools.restrict_to_workspace,
    )

    # Show spinner when logs are off (no output to miss); skip when logs are on
    def _thinking_ctx():
        if logs:
            from contextlib import nullcontext

            return nullcontext()
        # Animated spinner is safe to use with prompt_toolkit input handling
        return console.status("[dim]nanocrew is thinking...[/dim]", spinner="dots")

    if message:
        # Single message mode
        async def run_once():
            with _thinking_ctx():
                response = await agent_loop.process_direct(message, session_id)
            _print_agent_response(response, render_markdown=markdown)

        asyncio.run(run_once())
    else:
        # Interactive mode
        _init_prompt_session()
        console.print(
            f"{__logo__} Interactive mode (type [bold]exit[/bold] or [bold]Ctrl+C[/bold] to quit)\n"
        )

        def _exit_on_sigint(signum, frame):
            _restore_terminal()
            console.print("\nGoodbye!")
            os._exit(0)

        signal.signal(signal.SIGINT, _exit_on_sigint)

        async def run_interactive():
            while True:
                try:
                    _flush_pending_tty_input()
                    user_input = await _read_interactive_input_async()
                    command = user_input.strip()
                    if not command:
                        continue

                    if _is_exit_command(command):
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break

                    with _thinking_ctx():
                        response = await agent_loop.process_direct(user_input, session_id)
                    _print_agent_response(response, render_markdown=markdown)
                except KeyboardInterrupt:
                    _restore_terminal()
                    console.print("\nGoodbye!")
                    break
                except EOFError:
                    _restore_terminal()
                    console.print("\nGoodbye!")
                    break

        asyncio.run(run_interactive())


# ============================================================================
# Channel Commands
# ============================================================================


channels_app = typer.Typer(help="Manage channels")
app.add_typer(channels_app, name="channels")


@channels_app.command("status")
def channels_status():
    """Show channel status."""
    from nanocrew.config.loader import load_config

    config = load_config()

    table = Table(title="Channel Status")
    table.add_column("Channel", style="cyan")
    table.add_column("Enabled", style="green")
    table.add_column("Configuration", style="yellow")

    dc = config.channels.discord
    table.add_row("Discord", "✓" if dc.enabled else "✗", dc.gateway_url)

    # Feishu
    fs = config.channels.feishu
    fs_config = f"app_id: {fs.app_id[:10]}..." if fs.app_id else "[dim]not configured[/dim]"
    table.add_row("Feishu", "✓" if fs.enabled else "✗", fs_config)

    # Mochat
    mc = config.channels.mochat
    mc_base = mc.base_url or "[dim]not configured[/dim]"
    table.add_row("Mochat", "✓" if mc.enabled else "✗", mc_base)

    # Telegram
    tg = config.channels.telegram
    tg_config = f"token: {tg.token[:10]}..." if tg.token else "[dim]not configured[/dim]"
    table.add_row("Telegram", "✓" if tg.enabled else "✗", tg_config)

    # Slack
    slack = config.channels.slack
    slack_config = "socket" if slack.app_token and slack.bot_token else "[dim]not configured[/dim]"
    table.add_row("Slack", "✓" if slack.enabled else "✗", slack_config)

    console.print(table)


@channels_app.command("login")
def channels_login():
    """Link device via QR code."""
    console.print("[yellow]No channels require QR code login.[/yellow]")
    console.print("All supported channels use token-based authentication.")


# ============================================================================
# Agent Commands
# ============================================================================

agent_app = typer.Typer(help="Manage agents")
app.add_typer(agent_app, name="agent")


@agent_app.command("list")
def agent_list():
    """List all registered agents."""
    from nanocrew.config.loader import load_config

    config = load_config()

    table = Table(title="Agents")
    table.add_column("Name", style="cyan")
    table.add_column("Model", style="green")
    table.add_column("Workspace", style="yellow")

    for name, agent_config in config.agents.registry.items():
        workspace_display = agent_config.workspace.replace(str(Path.home()), "~")
        table.add_row(
            name + (" [dim](default)" if name == "main" else ""),
            agent_config.model,
            workspace_display,
        )

    console.print(table)

    # Show bindings if any
    if config.agents.bindings:
        console.print("\n[bold]Session Bindings:[/bold]")
        binding_table = Table()
        binding_table.add_column("Session", style="cyan")
        binding_table.add_column("Agent", style="green")
        for session, agent in config.agents.bindings.items():
            binding_table.add_row(session, agent)
        console.print(binding_table)


@agent_app.command("show")
def agent_show(name: str = typer.Argument(..., help="Agent name")):
    """Show detailed information about an agent."""
    from nanocrew.config.loader import load_config

    config = load_config()

    if name not in config.agents.registry:
        console.print(f"[red]Agent '{name}' not found.[/red]")
        console.print(f"Available agents: {', '.join(config.agents.registry.keys())}")
        raise typer.Exit(1)

    agent_config = config.agents.registry[name]

    console.print(f"[bold cyan]{name}[/bold cyan]")
    console.print(f"  Model: {agent_config.model}")
    console.print(f"  Temperature: {agent_config.temperature}")
    console.print(f"  Max Tokens: {agent_config.max_tokens}")
    console.print(f"  Max Tool Iterations: {agent_config.max_tool_iterations}")
    console.print(f"  Memory Window: {agent_config.memory_window}")
    console.print(f"  Workspace: {agent_config.workspace}")

    if agent_config.system_prompt:
        console.print(f"  System Prompt: {agent_config.system_prompt[:100]}...")


@agent_app.command("bind")
def agent_bind(
    session: str = typer.Argument(..., help="Session key (e.g., feishu:oc_xxx)"),
    agent_name: str = typer.Argument(..., help="Agent name to bind"),
):
    """Bind a session to an agent."""
    from nanocrew.config.loader import load_config, save_config

    config = load_config()

    if agent_name not in config.agents.registry:
        console.print(f"[red]Agent '{agent_name}' not found.[/red]")
        console.print(f"Available agents: {', '.join(config.agents.registry.keys())}")
        raise typer.Exit(1)

    config.agents.bindings[session] = agent_name
    save_config(config)

    console.print(f"[green]✓[/green] Bound session '{session}' to agent '{agent_name}'")


@agent_app.command("unbind")
def agent_unbind(
    session: str = typer.Argument(..., help="Session key to unbind"),
):
    """Remove a session-agent binding."""
    from nanocrew.config.loader import load_config, save_config

    config = load_config()

    if session not in config.agents.bindings:
        console.print(f"[yellow]Session '{session}' has no binding[/yellow]")
        raise typer.Exit(1)

    del config.agents.bindings[session]
    save_config(config)

    console.print(f"[green]✓[/green] Removed binding for session '{session}'")


@agent_app.command("create")
def agent_create(
    name: str = typer.Argument(..., help="Agent name"),
    workspace: str = typer.Option(None, "--workspace", "-w", help="Workspace path"),
    model: str = typer.Option(None, "--model", "-m", help="Model name"),
    temperature: float = typer.Option(
        None, "--temperature", "-t", help="Temperature (defaults to main agent's temperature)"
    ),
):
    """Create a new agent."""
    from nanocrew.config.loader import load_config, save_config
    from nanocrew.config.schema import AgentDefinition

    config = load_config()

    if name in config.agents.registry:
        console.print(f"[red]Agent '{name}' already exists.[/red]")
        raise typer.Exit(1)

    # Use main agent config as template
    main = config.agents.get_main_agent()
    agent_workspace = workspace or f"~/.nanocrew/workspaces/{name}"

    # Inherit from main
    agent_model = model or main.model
    agent_temperature = temperature if temperature is not None else main.temperature

    # Create agent with values copied from main
    config.agents.registry[name] = AgentDefinition(
        workspace=agent_workspace,
        model=agent_model,
        temperature=agent_temperature,
        max_tokens=main.max_tokens,
        max_tool_iterations=main.max_tool_iterations,
        memory_window=main.memory_window,
    )

    save_config(config)

    # Create workspace directory with full structure
    ws_path = Path(agent_workspace).expanduser()
    _create_agent_workspace(ws_path, name)

    console.print(f"[green]✓[/green] Created agent '{name}'")
    console.print(f"  Workspace: {agent_workspace}")
    console.print(f"  Model: {agent_model}")
    console.print(f"\nUse [bold]nanocrew agent bind <session> {name}[/bold] to bind a session")


def _create_agent_workspace(workspace: Path, agent_name: str) -> None:
    """Create complete workspace structure for a new agent."""
    from nanocrew.config.migration import ensure_agent_workspace

    ensure_agent_workspace(workspace, agent_name)


# ============================================================================
# Cron Commands
# ============================================================================

cron_app = typer.Typer(help="Manage scheduled tasks")
app.add_typer(cron_app, name="cron")


@cron_app.command("list")
def cron_list(
    all: bool = typer.Option(False, "--all", "-a", help="Include disabled jobs"),
):
    """List scheduled jobs."""
    from nanocrew.config.loader import get_data_dir
    from nanocrew.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    jobs = service.list_jobs(include_disabled=all)

    if not jobs:
        console.print("No scheduled jobs.")
        return

    table = Table(title="Scheduled Jobs")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Schedule")
    table.add_column("Status")
    table.add_column("Next Run")

    import time

    for job in jobs:
        # Format schedule
        if job.schedule.kind == "every":
            sched = f"every {(job.schedule.every_ms or 0) // 1000}s"
        elif job.schedule.kind == "cron":
            sched = job.schedule.expr or ""
        else:
            sched = "one-time"

        # Format next run
        next_run = ""
        if job.state.next_run_at_ms:
            next_time = time.strftime(
                "%Y-%m-%d %H:%M", time.localtime(job.state.next_run_at_ms / 1000)
            )
            next_run = next_time

        status = "[green]enabled[/green]" if job.enabled else "[dim]disabled[/dim]"

        table.add_row(job.id, job.name, sched, status, next_run)

    console.print(table)


@cron_app.command("add")
def cron_add(
    name: str = typer.Option(..., "--name", "-n", help="Job name"),
    message: str = typer.Option(..., "--message", "-m", help="Message for agent"),
    every: int = typer.Option(None, "--every", "-e", help="Run every N seconds"),
    cron_expr: str = typer.Option(None, "--cron", "-c", help="Cron expression (e.g. '0 9 * * *')"),
    at: str = typer.Option(None, "--at", help="Run once at time (ISO format)"),
    deliver: bool = typer.Option(False, "--deliver", "-d", help="Deliver response to channel"),
    to: str = typer.Option(None, "--to", help="Recipient for delivery"),
    channel: str = typer.Option(
        None, "--channel", help="Channel for delivery (e.g. 'telegram', 'whatsapp')"
    ),
):
    """Add a scheduled job."""
    from nanocrew.config.loader import get_data_dir
    from nanocrew.cron.service import CronService
    from nanocrew.cron.types import CronSchedule

    # Determine schedule type
    if every:
        schedule = CronSchedule(kind="every", every_ms=every * 1000)
    elif cron_expr:
        schedule = CronSchedule(kind="cron", expr=cron_expr)
    elif at:
        import datetime

        dt = datetime.datetime.fromisoformat(at)
        schedule = CronSchedule(kind="at", at_ms=int(dt.timestamp() * 1000))
    else:
        console.print("[red]Error: Must specify --every, --cron, or --at[/red]")
        raise typer.Exit(1)

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    job = service.add_job(
        name=name,
        schedule=schedule,
        message=message,
        deliver=deliver,
        to=to,
        channel=channel,
    )

    console.print(f"[green]✓[/green] Added job '{job.name}' ({job.id})")


@cron_app.command("remove")
def cron_remove(
    job_id: str = typer.Argument(..., help="Job ID to remove"),
):
    """Remove a scheduled job."""
    from nanocrew.config.loader import get_data_dir
    from nanocrew.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    if service.remove_job(job_id):
        console.print(f"[green]✓[/green] Removed job {job_id}")
    else:
        console.print(f"[red]Job {job_id} not found[/red]")


@cron_app.command("enable")
def cron_enable(
    job_id: str = typer.Argument(..., help="Job ID"),
    disable: bool = typer.Option(False, "--disable", help="Disable instead of enable"),
):
    """Enable or disable a job."""
    from nanocrew.config.loader import get_data_dir
    from nanocrew.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    job = service.enable_job(job_id, enabled=not disable)
    if job:
        status = "disabled" if disable else "enabled"
        console.print(f"[green]✓[/green] Job '{job.name}' {status}")
    else:
        console.print(f"[red]Job {job_id} not found[/red]")


@cron_app.command("run")
def cron_run(
    job_id: str = typer.Argument(..., help="Job ID to run"),
    force: bool = typer.Option(False, "--force", "-f", help="Run even if disabled"),
):
    """Manually run a job."""
    from nanocrew.config.loader import get_data_dir
    from nanocrew.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    async def run():
        return await service.run_job(job_id, force=force)

    if asyncio.run(run()):
        console.print(f"[green]✓[/green] Job executed")
    else:
        console.print(f"[red]Failed to run job {job_id}[/red]")


# ============================================================================
# Status Commands
# ============================================================================


@app.command()
def status():
    """Show nanocrew status."""
    from nanocrew.config.loader import load_config, get_config_path

    config_path = get_config_path()
    config = load_config()
    workspace = config.workspace_path

    console.print(f"{__logo__} nanocrew Status\n")

    console.print(
        f"Config: {config_path} {'[green]✓[/green]' if config_path.exists() else '[red]✗[/red]'}"
    )
    console.print(
        f"Workspace: {workspace} {'[green]✓[/green]' if workspace.exists() else '[red]✗[/red]'}"
    )

    if config_path.exists():
        from nanocrew.providers.registry import PROVIDERS

        main = config.agents.get_main_agent()
        console.print(f"Model: {main.model}")

        # Check API keys from registry
        for spec in PROVIDERS:
            p = getattr(config.providers, spec.name, None)
            if p is None:
                continue
            if spec.is_local:
                # Local deployments show api_base instead of api_key
                if p.api_base:
                    console.print(f"{spec.label}: [green]✓ {p.api_base}[/green]")
                else:
                    console.print(f"{spec.label}: [dim]not set[/dim]")
            else:
                has_key = bool(p.api_key)
                console.print(
                    f"{spec.label}: {'[green]✓[/green]' if has_key else '[dim]not set[/dim]'}"
                )


if __name__ == "__main__":
    app()

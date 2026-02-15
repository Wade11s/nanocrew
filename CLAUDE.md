# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

nanobot is an ultra-lightweight (~4,000 lines) personal AI assistant framework. It uses a modular architecture with async message passing between components.

## Common Commands

### Development Setup
```bash
# Using pip
pip install -e ".[dev]"    # Install from source with dev dependencies

# Using uv (faster)
uv pip install -e ".[dev]"

nanobot onboard             # Initialize config (~/.nanobot/config.json) and workspace
```

### Running the Agent
```bash
nanobot agent -m "Hello!"              # Single message
nanobot agent                          # Interactive mode (exit with Ctrl+D or 'exit')
nanobot agent --no-markdown            # Plain text output
nanobot agent --logs                   # Show runtime logs during chat
nanobot gateway                        # Start gateway (connects to enabled channels)
nanobot gateway -v                     # Verbose gateway mode
```

### Testing and Linting
```bash
pytest                          # Run all tests
pytest tests/test_commands.py  # Run specific test file
pytest -k test_name            # Run specific test
ruff check .                   # Lint
ruff format .                  # Format code
```

### Utility Commands
```bash
nanobot status                          # Show configuration status
nanobot channels status                 # Show channel configuration
bash core_agent_lines.sh               # Count lines of core agent code

# Cron jobs
nanobot cron add --name "daily" --message "Good morning!" --cron "0 9 * * *"
nanobot cron add --name "hourly" --message "Check status" --every 3600
nanobot cron list
nanobot cron remove <job_id>
```

### Docker
```bash
# Build the image
docker build -t nanobot .

# Initialize config (first time only)
docker run -v ~/.nanobot:/root/.nanobot --rm nanobot onboard

# Run gateway
docker run -v ~/.nanobot:/root/.nanobot -p 18790:18790 nanobot gateway

# Run single command
docker run -v ~/.nanobot:/root/.nanobot --rm nanobot agent -m "Hello!"
```

## High-Level Architecture

### Message Flow
```
Channel → InboundMessage → MessageBus.inbound → AgentLoop.process()
                                            ↓
AgentLoop → OutboundMessage → MessageBus.outbound → ChannelManager.dispatch() → Channel.send()
```

### Core Components

**Agent Loop** (`nanobot/agent/loop.py`): The central processing engine. Receives messages from the bus, builds context (system prompt + history + skills), calls the LLM, executes tool calls in a loop, and sends responses. Registered tools: filesystem (read/write/edit/list), shell exec, web search/fetch, message, spawn (subagent), cron.

**Tool System** (`nanobot/agent/tools/`): Tools inherit from `Tool` base class with JSON Schema parameters. The `ToolRegistry` handles validation and execution. Safety features: path restrictions (when `restrict_to_workspace=true`), command deny patterns for destructive operations, timeouts for shell commands.

**Channels** (`nanobot/channels/`): Each chat platform implements `BaseChannel` (start/stop/send methods). Supported: Telegram, Discord, Feishu, DingTalk, Slack, Email, QQ, Mochat. All channels use allowlist-based access control via `is_allowed()`.

**Provider System** (`nanobot/providers/`): Uses LiteLLM for multi-provider support. The `ProviderSpec` registry in `registry.py` is the single source of truth. Adding a provider requires: (1) add `ProviderSpec` to `PROVIDERS`, (2) add field to `ProvidersConfig` in `config/schema.py`. Supports 15+ providers including OpenRouter, Anthropic, OpenAI, DeepSeek, Gemini, Groq, Zhipu, DashScope, Moonshot, MiniMax, vLLM.

**Skills** (`nanobot/agent/skills.py`): Markdown-based skill definitions with YAML frontmatter. Skills marked `always: true` load into every context; others are available on-demand via `read_file`. Requirements (binaries, env vars) are checked at runtime.

**Bus/Events** (`nanobot/bus/`): Async message queue decouples channels from the agent. `InboundMessage` and `OutboundMessage` are standardized formats that all channels use.

**Memory** (`nanobot/agent/memory.py`): Two-layer system: `MEMORY.md` (long-term facts) and `HISTORY.md` (searchable conversation log). Memory consolidation triggers when context window is exceeded.

**Configuration** (`nanobot/config/`): Pydantic models with JSON storage at `~/.nanobot/config.json`. Environment variable support: `NANOBOT_<PATH>__<TO>__<FIELD>`. Workspace path is configurable per agent; defaults to `~/.nanobot/workspaces/main/`.

**Sessions** (`nanobot/session/manager.py`): Persist to JSON files keyed by `channel:chat_id`. Sessions store message history append-only.

**Multi-Agent System** (`nanobot/agent/manager.py`, `nanobot/agent/registry.py`): Supports multiple isolated agents, each with independent workspace, model, and configuration. `AgentRegistry` handles session-to-agent binding resolution with hot reload. `MultiAgentManager` manages lazy AgentLoop instance creation per agent.

### Multi-Agent Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Multi-Agent System                       │
├─────────────────────────────────────────────────────────────┤
│  Channel (Feishu/Telegram/etc)                               │
│     ↓                                                        │
│  session_key = "feishu:oc_xxx"                               │
│     ↓                                                        │
│  AgentRegistry.get_agent_name_for_session(session_key)       │
│     ↓                                                        │
│  MultiAgentManager.get_loop_for_session(session_key)         │
│     ↓                                                        │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │
│  │  AgentLoop  │    │  AgentLoop  │    │  AgentLoop  │      │
│  │   (main)    │    │  (backend)  │    │  (product)  │      │
│  │  workspaces │    │  workspaces │    │  workspaces │      │
│  │    /main    │    │  /backend   │    │  /product   │      │
│  └─────────────┘    └─────────────┘    └─────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

**Key Concepts:**
- **Agent**: Named configuration with workspace, model, temperature, system prompt
- **Registry**: Maps session keys (e.g., `feishu:oc_abc123`) to agent names
- **Hot Reload**: Config changes detected via mtime, no restart needed
- **Lazy Creation**: AgentLoop instances created on first use
- **Isolation**: Each agent has separate workspace, memory, session history

**Directory Structure:**
```
~/.nanobot/
├── workspaces/
│   ├── main/              # Default agent
│   │   ├── AGENTS.md
│   │   ├── SOUL.md
│   │   ├── memory/
│   │   └── skills/
│   ├── backend_dev/       # Backend team agent
│   └── product/           # Product team agent
└── config.json
```

### Key Files for Common Tasks

| Task | Files |
|------|-------|
| Add LLM provider | `nanobot/providers/registry.py`, `nanobot/config/schema.py` |
| Add tool | `nanobot/agent/tools/*.py`, register in `loop.py` |
| Add channel | `nanobot/channels/base.py`, implement `BaseChannel`, register in `manager.py` |
| Modify agent behavior | `nanobot/agent/loop.py`, `nanobot/agent/context.py` |
| Change config schema | `nanobot/config/schema.py` |
| Add skill | Create `SKILL.md` in `nanobot/skills/` or workspace `skills/` |
| Add/manage agents | `nanobot agent create/bind/unbind` commands, config in `agents.registry` and `agents.bindings` |
| Modify multi-agent logic | `nanobot/agent/registry.py`, `nanobot/agent/manager.py` |
| Agent workspace templates | `nanobot/config/migration.py` |

### Testing Patterns

Tests use `mock_paths` fixture to isolate filesystem operations. CLI tests use Typer's `CliRunner`. Async tests use `pytest-asyncio`. Common pattern:

```python
@pytest.fixture
def mock_paths():
    with patch("nanobot.config.loader.get_config_path") as mock_cp, \
         patch("nanobot.utils.helpers.get_workspace_path") as mock_ws:
        # Setup temp paths
        yield config_file, workspace_dir
        # Cleanup
```

### Line Count Philosophy
The project maintains a small core (~4,000 lines). Run `bash core_agent_lines.sh` to verify. The script excludes `channels/`, `cli/`, and `providers/` from the core count.

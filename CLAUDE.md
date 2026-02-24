# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

nanocrew is an ultra-lightweight (~4,000 lines) personal AI assistant framework based on nanobot. It uses a modular architecture with async message passing between components and supports multiple isolated agents.

## Common Commands

### Development Setup

**必须使用 uv 管理所有 Python 环境：**

```bash
# 使用 uv 创建虚拟环境并激活
uv venv .venv
source .venv/bin/activate  # Linux/Mac
# 或: .venv\Scripts\activate  # Windows

# 使用 uv 安装依赖（所有 Python 操作必须使用 uv）
uv pip install -e ".[dev]"

nanocrew onboard             # Initialize config (~/.nanocrew/config.json) and workspace
```

**注意：** uv 管理所有 Python 相关事务，包括虚拟环境创建和依赖安装。禁止直接使用 pip 或 python -m venv。

### Running the Agent

```bash
nanocrew agent -m "Hello!"              # Single message
nanocrew agent                          # Interactive mode (exit with Ctrl+D or 'exit')
nanocrew agent --no-markdown            # Plain text output
nanocrew agent --logs                   # Show runtime logs during chat
nanocrew gateway                        # Start gateway (connects to enabled channels)
nanocrew gateway -v                     # Verbose gateway mode
```

### Multi-Agent Commands

```bash
nanocrew agent list                     # List all agents
nanocrew agent show <name>              # Show agent details
nanocrew agent create <name>            # Create new agent
nanocrew agent bind <session> <agent>   # Bind session to agent (e.g., feishu:oc_xxx backend_dev)
nanocrew agent unbind <session>         # Remove session binding
```

### Testing and Linting

**测试前确保已激活虚拟环境并安装了依赖：**

```bash
# 确保虚拟环境已激活
source .venv/bin/activate  # Linux/Mac
# 或: .venv\Scripts\activate  # Windows

# 运行测试
.venv/bin/python -m pytest                          # Run all tests
.venv/bin/python -m pytest tests/test_commands.py   # Run specific test file
.venv/bin/python -m pytest -k test_name             # Run specific test

# 代码检查和格式化
ruff check .                   # Lint
ruff format .                  # Format code
```

**注意：** 所有测试必须在虚拟环境中运行，使用 uv 安装的依赖。

### Utility Commands

```bash
nanocrew status                          # Show configuration status
nanocrew channels status                 # Show channel configuration
bash core_agent_lines.sh                 # Count lines of core agent code

# Cron jobs
nanocrew cron add --name "daily" --message "Good morning!" --cron "0 9 * * *"
nanocrew cron add --name "hourly" --message "Check status" --every 3600
nanocrew cron list
nanocrew cron remove <job_id>
```

### Docker

```bash
# Build the image
docker build -t nanocrew .

# Initialize config (first time only)
docker run -v ~/.nanocrew:/root/.nanocrew --rm nanocrew onboard

# Run gateway
docker run -v ~/.nanocrew:/root/.nanocrew -p 18790:18790 nanocrew gateway

# Run single command
docker run -v ~/.nanocrew:/root/.nanocrew --rm nanocrew agent -m "Hello!"
```

## High-Level Architecture

### Message Flow

```
Channel → InboundMessage → MessageBus.inbound → AgentLoop.process()
                                            ↓
AgentLoop → OutboundMessage → MessageBus.outbound → ChannelManager.dispatch() → Channel.send()
```

### Core Components

**Agent Loop** (`nanocrew/agent/loop.py`): The central processing engine. Receives messages from the bus, builds context (system prompt + history + skills), calls the LLM, executes tool calls in a loop, and sends responses. Registered tools: filesystem (read/write/edit/list), shell exec, web search/fetch, message, spawn (subagent), cron.

**Tool System** (`nanocrew/agent/tools/`): Tools inherit from `Tool` base class with JSON Schema parameters. The `ToolRegistry` handles validation and execution. Safety features: path restrictions (when `restrict_to_workspace=true`), command deny patterns for destructive operations, timeouts for shell commands.

**Channels** (`nanocrew/channels/`): Each chat platform implements `BaseChannel` (start/stop/send methods). Supported: Telegram, Discord, Feishu, DingTalk, Slack, Email, QQ, Mochat. All channels use allowlist-based access control via `is_allowed()`.

**Provider System** (`nanocrew/providers/`): Uses LiteLLM for multi-provider support. The `ProviderSpec` registry in `registry.py` is the single source of truth. Adding a provider requires: (1) add `ProviderSpec` to `PROVIDERS`, (2) add field to `ProvidersConfig` in `config/schema.py`. Supports 15+ providers including OpenRouter, Anthropic, OpenAI, DeepSeek, Gemini, Groq, Zhipu, DashScope, Moonshot, MiniMax, vLLM.

**Skills** (`nanocrew/agent/skills.py`): Markdown-based skill definitions with YAML frontmatter. Skills marked `always: true` load into every context; others are available on-demand via `read_file`. Requirements (binaries, env vars) are checked at runtime.

**Bus/Events** (`nanocrew/bus/`): Async message queue decouples channels from the agent. `InboundMessage` and `OutboundMessage` are standardized formats that all channels use.

**Memory** (`nanocrew/agent/memory.py`): Two-layer system: `MEMORY.md` (long-term facts) and `HISTORY.md` (searchable conversation log). Memory consolidation triggers when context window is exceeded.

**Configuration** (`nanocrew/config/`): Pydantic models with JSON storage at `~/.nanocrew/config.json`. Environment variable support: `NANOCREW_<PATH>__<TO>__<FIELD>`. Workspace path is configurable per agent; defaults to `~/.nanocrew/workspaces/main/`.

**Sessions** (`nanocrew/session/manager.py`): Persist to JSON files keyed by `channel:chat_id`. Sessions store message history append-only.

**Multi-Agent System** (`nanocrew/agent/manager.py`, `nanocrew/agent/registry.py`): Supports multiple isolated agents, each with independent workspace, model, and configuration. `AgentRegistry` handles session-to-agent binding resolution with hot reload. `MultiAgentManager` manages lazy AgentLoop instance creation per agent.

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
~/.nanocrew/
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

**Multi-Agent Configuration Example:**
```json
{
  "agents": {
    "registry": {
      "main": {
        "workspace": "~/.nanocrew/workspaces/main",
        "model": "anthropic/claude-sonnet-4",
        "temperature": 0.7
      },
      "backend_dev": {
        "workspace": "~/.nanocrew/workspaces/backend_dev",
        "model": "anthropic/claude-opus-4-5",
        "temperature": 0.3,
        "systemPrompt": "You are a backend development assistant."
      }
    },
    "bindings": {
      "feishu:oc_backend_group": "backend_dev",
      "telegram:123456789": "backend_dev"
    }
  }
}
```

### Key Files for Common Tasks

| Task | Files |
|------|-------|
| Add LLM provider | `nanocrew/providers/registry.py`, `nanocrew/config/schema.py` |
| Add tool | `nanocrew/agent/tools/*.py`, register in `loop.py` |
| Add channel | `nanocrew/channels/base.py`, implement `BaseChannel`, register in `manager.py` |
| Modify agent behavior | `nanocrew/agent/loop.py`, `nanocrew/agent/context.py` |
| Change config schema | `nanocrew/config/schema.py` |
| Add skill | Create `SKILL.md` in `nanocrew/skills/` or workspace `skills/` |
| Add/manage agents | `nanocrew agent create/bind/unbind` commands, config in `agents.registry` and `agents.bindings` |
| Modify multi-agent logic | `nanocrew/agent/registry.py`, `nanocrew/agent/manager.py` |
| Agent workspace templates | `nanocrew/config/migration.py` |

### Testing Patterns

Tests use `mock_paths` fixture to isolate filesystem operations. CLI tests use Typer's `CliRunner`. Async tests use `pytest-asyncio`. Common pattern:

```python
@pytest.fixture
def mock_paths():
    with patch("nanocrew.config.loader.get_config_path") as mock_cp, \
         patch("nanocrew.utils.helpers.get_workspace_path") as mock_ws:
        # Setup temp paths
        yield config_file, workspace_dir
        # Cleanup
```

### Line Count Philosophy

The project maintains a small core (~4,000 lines). Run `bash core_agent_lines.sh` to verify. The script excludes `channels/`, `cli/`, and `providers/` from the core count.

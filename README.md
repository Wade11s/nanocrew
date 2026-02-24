<div align="center">
  <h1>nanocrew: Multi-Agent AI Assistant Framework</h1>
  <p>
    <img src="https://img.shields.io/badge/python-≥3.11-blue" alt="Python">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  </p>
</div>

> **Based on [nanocrew](https://github.com/HKUDS/nanocrew)** — An ultra-lightweight personal AI assistant framework with multi-agent support.

🐈 **nanocrew** extends nanocrew with enhanced multi-agent capabilities, allowing you to run multiple isolated AI agents for different teams, projects, or use cases.

⚡️ Delivers core agent functionality in just **~4,000** lines of code.

## ✨ Key Features

🪶 **Ultra-Lightweight**: Just ~4,000 lines of core agent code.

🤖 **Multi-Agent System**: Run multiple isolated agents, each with its own workspace, model, and configuration.

🔬 **Research-Ready**: Clean, readable code that's easy to understand, modify, and extend.

💎 **Easy-to-Use**: One-click to deploy and you're ready to go.

## 🤖 Multi-Agent System

nanocrew supports multiple isolated agents, each with its own workspace, model, and configuration. Perfect for separating different teams, projects, or use cases.

### Quick Start

```bash
# List all agents
nanocrew agent list

# Create a new agent for backend development
nanocrew agent create backend_dev --temperature 0.3

# Bind a Feishu group to the backend agent
nanocrew agent bind feishu:oc_xxx backend_dev

# Show agent details
nanocrew agent show backend_dev
```

### Configuration

Multi-agent configuration in `~/.nanocrew/config.json`:

```json
{
  "agents": {
    "registry": {
      "main": {
        "workspace": "~/.nanocrew/workspaces/main",
        "model": "anthropic/claude-sonnet-4",
        "temperature": 0.7,
        "maxTokens": 8192
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

## 📦 Install

**Install from source** (recommended for development)

```bash
git clone https://github.com/Wade11s/nanocrew.git
cd nanocrew
pip install -e .
```

## 🚀 Quick Start

> [!TIP]
> Set your API key in `~/.nanocrew/config.json`.
> Get API keys: [OpenRouter](https://openrouter.ai/keys) (Global)

**1. Initialize**

```bash
nanocrew onboard
```

This creates:
- Config file at `~/.nanocrew/config.json`
- Main agent workspace at `~/.nanocrew/workspaces/main/`

**2. Configure** (`~/.nanocrew/config.json`)

```json
{
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-v1-xxx"
    }
  }
}
```

**3. Chat**

```bash
nanocrew agent -m "What is 2+2?"
```

## 💬 Chat Apps

Talk to your nanocrew through Telegram, Discord, Feishu, DingTalk, Slack, Email, or QQ.

| Channel | Setup |
|---------|-------|
| **Telegram** | Easy (just a token) |
| **Discord** | Easy (bot token + intents) |
| **Feishu** | Medium (app credentials) |
| **DingTalk** | Medium (app credentials) |
| **Slack** | Medium (bot + app tokens) |
| **Email** | Medium (IMAP/SMTP credentials) |
| **QQ** | Easy (app credentials) |

See detailed setup instructions in the original [nanocrew documentation](https://github.com/HKUDS/nanocrew).

## 🐳 Docker

```bash
# Build the image
docker build -t nanocrew .

# Initialize config (first time only)
docker run -v ~/.nanocrew:/root/.nanocrew --rm nanocrew onboard

# Edit config on host to add API keys
vim ~/.nanocrew/config.json

# Run gateway
docker run -v ~/.nanocrew:/root/.nanocrew -p 18790:18790 nanocrew gateway

# Run a single command
docker run -v ~/.nanocrew:/root/.nanocrew --rm nanocrew agent -m "Hello!"
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `nanocrew onboard` | Initialize config & workspace |
| `nanocrew agent -m "..."` | Chat with the agent |
| `nanocrew agent` | Interactive chat mode |
| `nanocrew agent list` | List all agents |
| `nanocrew agent show <name>` | Show agent details |
| `nanocrew agent create <name>` | Create new agent |
| `nanocrew agent bind <session> <agent>` | Bind session to agent |
| `nanocrew agent unbind <session>` | Remove session binding |
| `nanocrew gateway` | Start the gateway |
| `nanocrew status` | Show status |

## 📁 Project Structure

```
nanocrew/
├── agent/          # 🧠 Core agent logic
│   ├── loop.py     #    Agent loop
│   ├── manager.py  #    Multi-agent manager
│   ├── registry.py #    Agent registry
│   └── tools/      #    Built-in tools
├── channels/       # 📱 Chat channel integrations
├── skills/         # 🎯 Bundled skills
├── bus/            # 🚌 Message routing
├── cron/           # ⏰ Scheduled tasks
├── providers/      # 🤖 LLM providers
├── session/        # 💬 Conversation sessions
├── config/         # ⚙️ Configuration
└── cli/            # 🖥️ Commands
```

## 🙏 Acknowledgments

This project is based on [nanocrew](https://github.com/HKUDS/nanocrew) by HKUDS.

nanocrew is an ultra-lightweight (~4,000 lines) personal AI assistant framework with excellent architecture and clean code. nanocrew extends it with enhanced multi-agent capabilities while maintaining the original simplicity.

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

Copyright (c) 2025 nanocrew contributors
Copyright (c) 2025 Wade11s (nanocrew)

---

<p align="center">
  <em>Thanks for visiting ✨ nanocrew!</em>
</p>

# OpenHarness Usage Guide

Practical guide for running `oh` (OpenHarness) and `ohmo` (personal agent), including the CLI and React Terminal UI.

---

## Table of Contents

1. [Installation](#installation)
2. [First-Time Setup](#first-time-setup)
3. [CLI — `oh`](#cli--oh)
4. [Terminal UI (WebUI)](#terminal-ui-webui)
5. [ohmo — Personal Agent](#ohmo--personal-agent)
6. [Provider Configuration](#provider-configuration)
7. [Environment Variables](#environment-variables)
8. [Development](#development)

---

## Installation

### From PyPI

```bash
pip install openharness-ai
```

### From Source (recommended for development)

```bash
git clone https://github.com/HKUDS/OpenHarness.git
cd OpenHarness
uv sync --extra dev
```

Requires Python ≥ 3.10 and Node.js (for the React Terminal UI).

---

## First-Time Setup

Run the interactive setup wizard once to configure your provider and authentication:

```bash
oh setup
```

This walks you through:
- Choosing a provider (Anthropic, OpenAI, GitHub Copilot, Azure OpenAI, etc.)
- Authenticating (API key, device flow, or managed identity)
- Selecting a default model

Credentials are stored in `~/.openharness/credentials.json` and profiles in `~/.openharness/profiles.json`.

---

## CLI — `oh`

### Interactive Mode

Launching `oh` without flags starts the **React Terminal UI** (see [Terminal UI](#terminal-ui-webui)):

```bash
oh
```

### Non-Interactive / Scripted Mode

```bash
# Single prompt, print response, exit
oh -p "Summarize this codebase"

# JSON output for programmatic use
oh -p "List all Python files" --output-format json

# Stream JSON events in real-time (useful for piping)
oh -p "Fix the bug in main.py" --output-format stream-json
```

### Session Management

```bash
oh --continue               # Resume the most recent session in this directory
oh --resume                 # Open a session picker
oh --resume SESSION_ID      # Resume a specific session by ID
oh --name "my session"      # Name this session
```

### Model & Effort

```bash
oh --model sonnet            # Use Claude Sonnet (alias)
oh --model gpt-4o            # Use any model by ID
oh --effort high             # Set effort level: low | medium | high | max
oh --max-turns 20            # Limit agentic loop iterations
```

### Permissions & Safety

```bash
oh --permission-mode plan       # Read-only: block all file writes (safe exploration)
oh --permission-mode default    # Ask before writes (default)
oh --permission-mode full_auto  # Allow all operations without prompting
```

### Provider & API Overrides

```bash
oh --api-format openai --base-url https://api.openai.com/v1 --model gpt-4o
oh --api-key sk-...              # Override API key for this session
oh --api-format anthropic        # Force Anthropic protocol
```

### System Prompt

```bash
oh --system-prompt "You are a security auditor."
oh --append-system-prompt "Always explain your reasoning."
```

---

## Terminal UI (WebUI)

The "WebUI" for OpenHarness is a **React Terminal UI** (TUI) — a full-featured interface rendered in the terminal using React + Ink. It is not a browser-based web app.

### Starting the TUI

```bash
oh
```

### Features

| Feature | Description |
|---------|-------------|
| **Transcript Pane** | Full conversation history with markdown rendering |
| **Composer** | Multiline input with keyboard shortcuts |
| **Command Picker** | Type `/` to browse 54+ slash commands |
| **Status Bar** | Token counts, model info, current mode |
| **Permission Dialogs** | Interactive prompts for sensitive operations |
| **Todo Panel** | Live task tracking during multi-step work |
| **Agent Status** | Swarm/teammate status when using multi-agent mode |
| **Animated Feedback** | Spinners and progress indicators during tool calls |

### Keyboard Shortcuts (in TUI)

| Shortcut | Action |
|----------|--------|
| `Enter` | Submit message |
| `Shift+Enter` | New line in composer |
| `/` | Open command picker |
| `Ctrl+C` | Exit |
| `Esc` | Cancel current operation |

### Slash Commands (type `/` in TUI)

Common commands available in the command picker:

```
/help           Show all available commands
/clear          Clear the conversation
/model          Switch model mid-session
/mode           Change permission mode
/compact        Summarize conversation to save tokens
/todo           Show current task list
/cost           Show token usage and cost
/settings       Open settings
```

### Architecture

The TUI works as a split architecture:
1. **Frontend** (`frontend/terminal/` — React/TypeScript/Ink) renders the UI
2. **Backend** (`src/openharness/ui/backend_host.py`) runs the agent loop
3. Communication over a JSON event stream via stdio

Node modules are installed automatically on first launch via `npm install`.

---

## ohmo — Personal Agent

`ohmo` is a personal AI agent built on OpenHarness that connects to chat platforms (Slack, Telegram, Discord, Feishu) and can autonomously write code, run tests, and open PRs.

### Setup

```bash
ohmo init       # Initialize ~/.ohmo workspace
ohmo config     # Configure provider and channels (Slack/Telegram/Discord/Feishu)
```

### Running the Gateway

```bash
ohmo gateway start      # Start gateway as a background daemon
ohmo gateway run        # Run gateway in the foreground (for debugging)
ohmo gateway status     # Check if gateway is running
ohmo gateway restart    # Restart gateway
```

Once running, ohmo listens for messages in your configured chat channels.

### Interactive Chat (local)

```bash
ohmo            # Chat with ohmo directly in the terminal (React TUI)
ohmo -p "..."   # Single prompt, non-interactive
```

### Memory Management

```bash
ohmo memory list              # List saved memories
ohmo memory add "I prefer TypeScript over JavaScript"
ohmo memory remove MEMORY_NAME
```

### Personality Files

ohmo's behavior is shaped by editable markdown files in `~/.ohmo/`:

```bash
ohmo soul inspect     # View soul.md (long-term personality)
ohmo soul edit        # Edit soul.md
ohmo user inspect     # View user.md (your preferences)
ohmo user edit        # Edit user.md
```

### Workspace Structure

```
~/.ohmo/
├── soul.md           # Long-term personality and working style
├── identity.md       # Who ohmo is
├── user.md           # Your profile and preferences
├── BOOTSTRAP.md      # First-run instructions
├── gateway.json      # Channel and provider configuration
├── memory/           # Persistent memory files
├── logs/             # Gateway and session logs
└── .sessions/        # Saved session snapshots
```

---

## Provider Configuration

### List and Switch Profiles

```bash
oh provider list            # Show all configured provider profiles
oh provider use PROFILE     # Activate a profile
```

### Add a New Provider

```bash
oh provider add my-azure \
  --label "Azure OpenAI" \
  --provider azure_openai \
  --api-format openai \
  --auth-source azure_identity \
  --model gpt-4o
```

### Authentication Commands

```bash
oh auth login               # Login to active provider
oh auth login anthropic     # Login to a specific provider
oh auth status              # Show current auth and profile status
oh auth logout              # Clear stored credentials
oh auth copilot-login       # GitHub Copilot device flow
oh auth claude-login        # Bind Claude CLI subscription
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENHARNESS_ACTIVE_PROFILE` | Active provider profile name |
| `OPENHARNESS_MODEL` | Default model override |
| `OPENHARNESS_API_FORMAT` | API format: `anthropic`, `openai`, `copilot` |
| `OPENHARNESS_BASE_URL` | API base URL override |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_BASE_URL` | OpenAI-compatible base URL |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL |
| `OHMO_WORKSPACE` | Path to ohmo workspace (overrides `~/.ohmo`) |
| `OPENHARNESS_LOG_LEVEL` | Log level: `DEBUG`, `INFO`, `WARNING` |

A `.env` file in the project root is automatically loaded.

---

## Development

### Run Tests

```bash
uv run pytest -q                              # Unit tests
python scripts/test_harness_features.py       # Harness feature tests
python scripts/test_cli_flags.py              # CLI flag E2E tests
```

### Lint & Format

```bash
uv run ruff check src tests scripts
uv run ruff format src tests scripts
```

### Type Check

```bash
uv run mypy src/openharness
```

### Project Layout

```
OpenHarness/
├── src/openharness/        # Core agent engine
│   ├── cli.py              # `oh` CLI entry point
│   ├── ui/                 # Terminal UI launcher & backend
│   ├── engine/             # Agent loop
│   ├── tools/              # 43+ built-in tools
│   ├── api/                # Provider clients
│   ├── auth/               # Authentication
│   ├── config/             # Settings & profiles
│   ├── channels/           # Slack, Telegram, Discord, Feishu
│   ├── mcp/                # MCP client
│   ├── skills/             # Skill loading
│   └── swarm/              # Multi-agent coordination
├── ohmo/                   # Personal agent app
│   ├── cli.py              # `ohmo` CLI entry point
│   └── gateway/            # Gateway service
├── frontend/terminal/      # React Terminal UI (TypeScript + Ink)
├── tests/                  # Test suite
└── docs/                   # This guide and architecture docs
```

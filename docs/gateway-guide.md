# ohmo Gateway — Design and Usage Guide

The **ohmo gateway** is the production-facing entry point of OpenHarness. It connects messaging platforms (Telegram, Slack, Discord, Feishu) to a Claude-powered AI agent, maintaining conversation sessions and streaming responses in real time.

---

## Architecture Overview

```
  Telegram / Slack / Discord / Feishu
          │
          ▼
   ChannelManager          ← one adapter per platform
          │
          ▼
     MessageBus            ← two async queues (inbound / outbound)
          │
          ▼
  OhmoGatewayBridge        ← routes messages to sessions, cancels stale tasks
          │
          ▼
  SessionRuntimePool       ← one RuntimeBundle per session key
          │
          ▼
   OpenHarness Engine      ← inference + tool execution
          │
          ▼
  Claude API / Azure OpenAI / OpenAI-compatible
```

### Key Design Decisions

| Decision | Rationale |
|---|---|
| Async queue between channels and runtime | Channels and the inference engine run independently; the queue absorbs bursts and lets them proceed at their own pace |
| Session keyed by `channel:chat_id[:thread_id]` | Each conversation thread gets isolated memory and history |
| New message cancels prior task in same session | Prevents stale responses from an interrupted reply; the user's latest message always takes priority |
| Long polling (no inbound port) | Telegram polling requires no public endpoint, reducing attack surface for container deployments |
| `--max-replicas 1` on ACA | Session state lives in memory; multiple replicas would split sessions across instances |

---

## Component Reference

### 1. Channels (`openharness/channels/`)

Each channel is an adapter that wraps a platform SDK.

| File | Platform |
|---|---|
| `impl/telegram.py` | Telegram (long polling, markdown → HTML) |
| `impl/slack.py` | Slack Socket Mode |
| `impl/discord.py` | Discord gateway |
| `impl/feishu.py` | Feishu / Lark webhook |
| `impl/manager.py` | Orchestrates all channels, dispatches outbound messages |
| `impl/base.py` | `BaseChannel` — abstract class all channels inherit |

**`BaseChannel` interface:**
```python
async def start() -> None           # Long-running listener loop
async def stop() -> None            # Graceful shutdown
async def send(msg: OutboundMessage) -> None  # Deliver reply to platform
def is_allowed(sender_id: str) -> bool        # Per-channel allowlist check
```

**Session key formation** (thread-aware):
```
channel:chat_id              # default
channel:chat_id:thread_id    # Slack threads, Telegram reply threads
```

### 2. Message Bus (`channels/bus/`)

Two `asyncio.Queue` instances decouple channels from the runtime:

```
channels  →  bus.inbound   →  bridge  →  bus.outbound  →  channels
```

- `InboundMessage`: `channel`, `chat_id`, `sender_id`, `content`, `media`, `metadata`
- `OutboundMessage`: `channel`, `chat_id`, `content`, `metadata` (includes `_progress`, `_session_key`)

### 3. Gateway Bridge (`ohmo/gateway/bridge.py`)

The bridge is the routing core. Its main loop:

1. Consume from `bus.inbound` (1-second timeout, non-blocking)
2. Compute `session_key` via `session_key_for_message()`
3. Handle built-in commands: `/stop` (cancels session), `/restart` (reloads gateway)
4. Cancel any in-flight task for the same session
5. Spawn `_process_message()` as an async task

`_process_message()` pipeline:
1. Build user message with speaker context and media
2. Get or create `RuntimeBundle` for the session key
3. Detect slash commands (e.g., `/plan`, `/permissions`) — execute handler if matched
4. Otherwise: submit to inference engine
5. Emit `GatewayStreamUpdate` events:
   - `kind="progress"` — thinking / tool hints (e.g., `🤔 Thinking…`)
   - `kind="final"` — complete response
   - `kind="error"` — exception with user-facing message
6. Save session snapshot to disk
7. Publish outbound messages back to `bus.outbound`

### 4. Session Runtime Pool (`ohmo/gateway/runtime.py`)

A `RuntimeBundle` is created once per `session_key` and reused for the lifetime of that conversation thread.

**Contents:**
- `session_id` — UUID, used for snapshot filenames
- `engine` — `ConversationEngine` with full message history
- Tool registry, plugin registry, MCP clients
- Current settings (model, permissions, etc.)

**Persistence** (`~/.ohmo/sessions/` or `$OHMO_WORKSPACE/sessions/`):
```
sessions/
├── latest.json               # Last session snapshot (quick resume)
└── latest-{token}.json       # Per-session-key snapshot (sha1 of session_key, first 12 chars)
```

Snapshot content: full message history, tool metadata, token usage, system prompt, timestamps.

### 5. Providers and Authentication

The gateway selects a provider via `OPENHARNESS_ACTIVE_PROFILE` (or `OHMO_PROVIDER_PROFILE` in `gateway.json`).

| Profile | Auth method | Key env vars |
|---|---|---|
| `azure-openai` | Entra ID / Managed Identity | `ENDPOINT_URL`, `AZURE_CLIENT_ID` |
| `anthropic` | API key | `ANTHROPIC_API_KEY` |
| `openai-compatible` | API key | `OPENAI_API_KEY`, `OPENAI_BASE_URL` |
| `copilot` | OAuth device flow | (interactive) |

**Azure OpenAI auth flow (container):**
```
Container starts
  → AZURE_CLIENT_ID env var set
  → DefaultAzureCredential selects App Service managed identity
  → Token issued for cognitiveservices.azure.com
  → AsyncAzureOpenAI uses token provider (no API key stored)
```

**Local development** (no `AZURE_CLIENT_ID` needed):
```
DefaultAzureCredential falls through to AzureCliCredential
  → uses your active az login session
```

---

## Configuration

### Gateway Config File (`~/.ohmo/gateway.json`)

```json
{
  "provider_profile": "azure-openai",
  "enabled_channels": ["telegram"],
  "send_progress": true,
  "send_tool_hints": true,
  "permission_mode": "full_auto",
  "sandbox_enabled": false,
  "allow_remote_admin_commands": false,
  "log_level": "INFO",
  "channel_configs": {
    "telegram": {
      "token": "<bot-token>",
      "allow_from": ["*"],
      "reply_to_message": true
    },
    "slack": {
      "bot_token": "xoxb-...",
      "app_token": "xapp-...",
      "allow_from": ["U12345678"],
      "reply_in_thread": true,
      "group_policy": "mention"
    }
  }
}
```

**`allow_from`**: `["*"]` allows anyone; replace with Telegram user IDs or Slack member IDs to restrict access.

**`group_policy`** (Slack/Discord only):
- `mention` — bot only responds when @-mentioned in channels (default)
- `open` — responds to all messages
- `allowlist` — only users in `allow_from`

**`permission_mode`**:
- `full_auto` — all tools run without approval prompts (recommended for unattended deployment)
- `default` — tools follow their individual permission settings

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `OHMO_TELEGRAM_TOKEN` | Yes (Telegram) | Bot token; triggers auto-generation of `gateway.json` in container |
| `ENDPOINT_URL` | Yes (Azure) | Azure OpenAI endpoint URL (no trailing newline) |
| `AZURE_CLIENT_ID` | Yes (ACA) | Managed identity client ID; omit for local dev |
| `OPENHARNESS_ACTIVE_PROFILE` | Yes | Provider profile (`azure-openai`, `anthropic`, …) |
| `OHMO_PROVIDER_PROFILE` | No | Written into generated `gateway.json`; same as `OPENHARNESS_ACTIVE_PROFILE` |
| `OHMO_PERMISSION_MODE` | No | `full_auto` or `default` |
| `OHMO_LOG_LEVEL` | No | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `OHMO_WORKSPACE` | No | Workspace root (default: `~/.ohmo` locally, `/data/ohmo` in container) |

### Workspace Layout

```
~/.ohmo/                        (OHMO_WORKSPACE)
├── gateway.json                Gateway config
├── state.json                  Runtime state (pid, running, active sessions)
├── soul.md                     Agent persona / system prompt base
├── user.md                     User profile injected into system prompt
├── identity.md                 Agent identity
├── memory/                     Persistent memory entries
│   ├── MEMORY.md               Index
│   └── *.md
├── sessions/                   Conversation snapshots
│   ├── latest.json
│   └── latest-{token}.json
├── attachments/                Downloaded media from channels
│   ├── telegram/
│   └── slack/
├── skills/                     Custom skill modules (auto-discovered)
├── plugins/                    Custom MCP plugins (auto-discovered)
└── logs/
    └── gateway.log
```

---

## Running the Gateway

### Local (foreground — recommended for development)

```bash
# First time: initialize workspace and configure channels
ohmo init
ohmo config

# Run in foreground; Ctrl+C to stop
ohmo gateway run
```

Logs print directly to the terminal. Useful for debugging.

### Local (background)

```bash
ohmo gateway start          # Starts in background, writes PID to ~/.ohmo/gateway.pid
ohmo gateway status         # Shows running, pid, active_sessions
ohmo gateway stop
ohmo gateway restart        # Reloads config without losing sessions

tail -f ~/.ohmo/logs/gateway.log
```

**Important**: Only one gateway process per bot token. Running a second process against the same Telegram token causes:
```
telegram.error.Conflict: terminated by other getUpdates request
```

### Docker

```bash
docker build -t ohmo-gateway:latest .

docker run -d \
  --name ohmo-gateway \
  -v ohmo-workspace:/data/ohmo \
  -e OHMO_TELEGRAM_TOKEN="<token>" \
  -e ENDPOINT_URL="https://<name>.openai.azure.com/" \
  -e AZURE_CLIENT_ID="<client-id>" \
  -e OHMO_PROVIDER_PROFILE="azure-openai" \
  -e OPENHARNESS_ACTIVE_PROFILE="azure-openai" \
  -e OHMO_PERMISSION_MODE="full_auto" \
  ohmo-gateway:latest
```

The `docker-entrypoint.sh` auto-generates `gateway.json` from env vars if `OHMO_TELEGRAM_TOKEN` is set.

### Azure Container Apps

See [deploy-aca.md](deploy-aca.md) for the full ACA deployment walkthrough including managed identity setup, Log Analytics, and persistent storage.
docker run -it \
  -e ENDPOINT_URL="https://datacopilothub8882317788.openai.azure.com/" \
  -e AZURE_CLIENT_ID="c9427d44-98e2-406a-9527-f7fa7059f984" \
  -e OPENHARNESS_ACTIVE_PROFILE="azure-openai" \
  -v ohmo-workspace:/data/ohmo \
  ohmo-gateway:latest \
  ohmo --workspace /data/ohmo --cwd /app

---

## CLI Reference

```bash
# Lifecycle
ohmo gateway run            # Foreground
ohmo gateway start          # Background daemon
ohmo gateway stop
ohmo gateway restart
ohmo gateway status

# Setup
ohmo init                   # Initialize workspace files
ohmo config                 # Interactive config wizard

# Agent persona
ohmo soul show
ohmo soul edit

# Memory
ohmo memory list
ohmo memory add "Title" "Content"
ohmo memory remove "title"

# Direct inference (no gateway)
ohmo --print "What is 2+2?"     # Single-turn
ohmo --continue                  # Resume last session
ohmo --resume <session-id>       # Resume specific session
ohmo --tui                       # Interactive TUI
```

---

## Troubleshooting

**`Conflict: terminated by other getUpdates request`**
More than one process is running with the same bot token. Find and kill the duplicate:
```bash
pgrep -la "ohmo"
pgrep -la "openharness"
# Kill the conflicting PID
kill <pid>
```

**`API error: Invalid non-printable ASCII character in URL, '\n' at position 50`**
The `ENDPOINT_URL` secret contains an embedded newline. When setting secrets from shell, always strip whitespace:
```bash
ENDPOINT_URL=$(grep -m 1 'base_url:' ~/.hermes/config.yaml | awk '{print $2}' | tr -d '\n')
```
Then update the running container secret and restart the revision.

**`Incomplete environment configuration for EnvironmentCredential`**
Expected when `AZURE_CLIENT_ID` is set but `AZURE_TENANT_ID` / `AZURE_CLIENT_SECRET` are not — `DefaultAzureCredential` falls through to Managed Identity automatically. This is an `INFO` log, not an error.

**`ManagedIdentityCredential will use App Service managed identity`**
Correct behavior in ACA. Confirms the managed identity is being used.

**Bot doesn't respond after ACA deploy**
1. Check logs: `az containerapp logs show --name <app> --resource-group <rg> --follow`
2. Look for `Telegram bot @<name> connected` — if missing, the token is wrong or the secret has a newline
3. Verify the secret value: `az containerapp show --name <app> --resource-group <rg> --query "properties.configuration.secrets"`

**Sessions lost after container restart**
Sessions are stored in `$OHMO_WORKSPACE`. Without a persistent volume, they are lost when the container restarts. Mount an Azure File Share at `/data/ohmo` — see [deploy-aca.md §8](deploy-aca.md#8-persistent-session-storage-optional-but-recommended).

**Tool prompts blocking responses**
A stale session snapshot has pending tool approvals. Clear session state:
```bash
# In ACA exec, or locally:
rm ~/.ohmo/sessions/latest-*.json
# Then restart the gateway / revision
```

---

## Extending the Gateway

### Add a New Channel

1. Create `openharness/channels/impl/<name>.py` inheriting `BaseChannel`
2. Implement `start()`, `stop()`, `send()`
3. Call `await self._handle_message(...)` when a message arrives
4. Add a config model (`<Name>Config`) and register in `ChannelManager._init_channels()`

### Add a New Provider

1. Create a client class implementing the `SupportsStreamingMessages` protocol:
   ```python
   async def stream_message(request: ApiMessageRequest) -> AsyncIterator[ApiStreamEvent]:
       ...
   ```
2. Register in the provider detection layer (`openharness/api/provider.py`)
3. Add an auth status check to `AuthManager`

### Custom Skills and Plugins

Place `.py` files in:
- `~/.ohmo/skills/` — custom slash commands and agent skills
- `~/.ohmo/plugins/` — MCP-compatible tool plugins

The gateway auto-discovers them at startup. No restart required after adding new files — use `ohmo gateway restart`.

# WebUI Chat Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a browser-based chat interface (React+Vite SPA) connected to the ohmo gateway via SSE, deployable locally and on ACA alongside the existing Telegram integration.

**Architecture:** A new `WebUIChannel` (implementing `BaseChannel`) embeds a FastAPI/Uvicorn HTTP server in the gateway process, exposing `POST /api/chat` and `GET /api/stream` (SSE). The React SPA lives in `frontend/web/` and talks to this API. On ACA, nginx serves the SPA and proxies `/api/` to the gateway's internal ingress, eliminating CORS entirely.

**Tech Stack:** Python: `fastapi>=0.115`, `uvicorn[standard]>=0.30`, `httpx` (test). Frontend: React 18, Vite 5, TypeScript, Vitest, MSW 2.

---

## File Map

### New files
| Path | Responsibility |
|---|---|
| `src/openharness/channels/impl/webui.py` | `WebUIChannel` — FastAPI server, SSE queue registry, send() routing |
| `tests/test_channels/test_webui.py` | Backend tests: POST/SSE/disconnect/session-key |
| `frontend/web/package.json` | Vite+React+TypeScript+Vitest+MSW deps |
| `frontend/web/vite.config.ts` | Dev proxy `/api → localhost:8080`, Vitest config |
| `frontend/web/tsconfig.json` | TypeScript config |
| `frontend/web/index.html` | SPA entry |
| `frontend/web/src/main.tsx` | React root mount |
| `frontend/web/src/types.ts` | `GatewayEvent`, `Message`, `SessionInfo`, `ConnectionStatus` |
| `frontend/web/src/hooks/useGatewaySession.ts` | EventSource + fetch, streaming state |
| `frontend/web/src/hooks/useGatewaySession.test.ts` | Vitest tests for hook |
| `frontend/web/src/components/App.tsx` | Sidebar + ChatPane layout |
| `frontend/web/src/components/SessionSidebar.tsx` | Session list, new-chat button |
| `frontend/web/src/components/ChatPane.tsx` | Message list + composer |
| `frontend/web/src/components/MessageBubble.tsx` | User/assistant bubble |
| `frontend/web/src/components/StreamingBubble.tsx` | Live delta text + spinner |
| `frontend/web/src/components/StatusBar.tsx` | Connection/thinking indicator |
| `frontend/web/src/test/setup.ts` | MSW + Vitest setup |
| `frontend/web/Dockerfile` | 2-stage: Node build → nginx serve |
| `frontend/web/nginx.conf` | SPA routing + `/api/` proxy + `/config.js` injection |

### Modified files
| Path | Change |
|---|---|
| `pyproject.toml` | Add `fastapi`, `uvicorn[standard]` to dependencies |
| `src/openharness/config/schema.py` | Add `WebUIConfig`, add `webui: WebUIConfig` to `ChannelConfigs` |
| `src/openharness/channels/impl/manager.py` | Add webui block in `_init_channels()` |
| `docker-entrypoint.sh` | Generate webui config block when `WEBUI_PORT` is set |
| `deploy.sh` | Add gateway ingress enable + `ohmo-webui` ACA app create |
| `.gitignore` | Add `.superpowers/` |

---

## Task 1: Add backend dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add fastapi and uvicorn to dependencies**

In `pyproject.toml`, add to the `dependencies` list:

```toml
dependencies = [
    "anthropic>=0.40.0",
    "openai>=1.0.0",
    "azure-identity>=1.19.0",
    "python-dotenv>=1.0.0",
    "rich>=13.0.0",
    "prompt-toolkit>=3.0.0",
    "textual>=0.80.0",
    "typer>=0.12.0",
    "pydantic>=2.0.0",
    "httpx>=0.27.0",
    "websockets>=12.0",
    "mcp>=1.0.0",
    "pyperclip>=1.9.0",
    "pyyaml>=6.0",
    "questionary>=2.0.1",
    "watchfiles>=0.20.0",
    "croniter>=2.0.0",
    "slack-sdk>=3.0.0",
    "python-telegram-bot>=21.0.0",
    "discord.py>=2.0.0",
    "lark-oapi>=1.5.0",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
]
```

- [ ] **Step 2: Re-install and verify import**

```bash
cd /Volumes/ExternalSSD/train/OpenHarness
pip install -e ".[dev]" -q
python -c "import fastapi, uvicorn; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add fastapi and uvicorn dependencies for WebUIChannel"
```

---

## Task 2: WebUIConfig schema

**Files:**
- Modify: `src/openharness/config/schema.py`
- Test: `tests/test_config/test_webui_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config/test_webui_config.py`:

```python
from openharness.config.schema import Config, WebUIConfig


def test_webui_config_defaults():
    cfg = WebUIConfig()
    assert cfg.port == 8080
    assert cfg.allow_from == ["*"]
    assert cfg.cors_origins == []
    assert cfg.enabled is False


def test_channel_configs_has_webui_field():
    config = Config()
    assert hasattr(config.channels, "webui")
    assert isinstance(config.channels.webui, WebUIConfig)


def test_webui_config_enabled_via_dict():
    cfg = WebUIConfig(enabled=True, port=9090, cors_origins=["http://localhost:5173"])
    assert cfg.enabled is True
    assert cfg.port == 9090
    assert "http://localhost:5173" in cfg.cors_origins
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_config/test_webui_config.py -v
```

Expected: `FAILED — ImportError: cannot import name 'WebUIConfig'`

- [ ] **Step 3: Add WebUIConfig to schema.py**

In `src/openharness/config/schema.py`, add after `MochatConfig`:

```python
class WebUIConfig(BaseChannelConfig):
    port: int = 8080
    cors_origins: list[str] = Field(default_factory=list)
```

And in `ChannelConfigs`, add:

```python
class ChannelConfigs(_CompatModel):
    send_progress: bool = True
    send_tool_hints: bool = True
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)
    dingtalk: DingTalkConfig = Field(default_factory=DingTalkConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    qq: QQConfig = Field(default_factory=QQConfig)
    matrix: MatrixConfig = Field(default_factory=MatrixConfig)
    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)
    mochat: MochatConfig = Field(default_factory=MochatConfig)
    webui: WebUIConfig = Field(default_factory=WebUIConfig)
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
pytest tests/test_config/test_webui_config.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/openharness/config/schema.py tests/test_config/test_webui_config.py
git commit -m "feat(config): add WebUIConfig schema and register in ChannelConfigs"
```

---

## Task 3: WebUIChannel implementation

**Files:**
- Create: `src/openharness/channels/impl/webui.py`
- Create: `tests/test_channels/test_webui.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_channels/test_webui.py`:

```python
"""Tests for WebUIChannel — FastAPI SSE gateway channel."""
from __future__ import annotations

import asyncio
import json

import pytest
import httpx
from httpx import AsyncClient, ASGITransport

from openharness.channels.bus.events import OutboundMessage
from openharness.channels.bus.queue import MessageBus
from openharness.channels.impl.webui import WebUIChannel
from openharness.config.schema import WebUIConfig


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def channel(bus):
    cfg = WebUIConfig(enabled=True, port=8080, allow_from=["*"])
    return WebUIChannel(cfg, bus)


@pytest.fixture
def client(channel):
    return AsyncClient(transport=ASGITransport(app=channel._app), base_url="http://test")


async def test_post_chat_enqueues_inbound_message(client, bus):
    resp = await client.post("/api/chat", json={"session_id": "s1", "message": "hello"})
    assert resp.status_code == 202
    msg = await asyncio.wait_for(bus.inbound.get(), timeout=1.0)
    assert msg.content == "hello"
    assert msg.channel == "webui"
    assert msg.chat_id == "s1"


async def test_session_key_format(client, bus):
    await client.post("/api/chat", json={"session_id": "abc", "message": "ping"})
    msg = await asyncio.wait_for(bus.inbound.get(), timeout=1.0)
    assert msg.session_key == "webui:abc"


async def test_sse_stream_receives_outbound_message(channel, client):
    async def push_after_connect():
        await asyncio.sleep(0.05)
        await channel.send(OutboundMessage(
            channel="webui",
            chat_id="s2",
            content="Hello from agent",
            metadata={},
        ))

    asyncio.create_task(push_after_connect())

    events = []
    async with client.stream("GET", "/api/stream?session_id=s2") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        async for line in resp.aiter_lines():
            if line.startswith("data:"):
                data = json.loads(line[5:].strip())
                events.append(data)
                if data.get("type") in ("final", "progress"):
                    break

    assert any(e.get("message") == "Hello from agent" for e in events)


async def test_disconnect_cleans_up_queue(channel, client):
    # Connect and immediately disconnect
    async with client.stream("GET", "/api/stream?session_id=cleanup-test") as resp:
        assert resp.status_code == 200
        # Just read one line then break (simulates disconnect)
        async for _ in resp.aiter_lines():
            break

    # Queue should have been removed (may take a moment)
    await asyncio.sleep(0.1)
    assert "cleanup-test" not in channel._queues
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_channels/test_webui.py -v
```

Expected: `ERROR — ModuleNotFoundError: No module named 'openharness.channels.impl.webui'`

- [ ] **Step 3: Implement WebUIChannel**

Create `src/openharness/channels/impl/webui.py`:

```python
"""WebUI channel — exposes the gateway over HTTP/SSE for browser clients."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from openharness.channels.bus.events import OutboundMessage
from openharness.channels.bus.queue import MessageBus
from openharness.channels.impl.base import BaseChannel
from openharness.config.schema import WebUIConfig

logger = logging.getLogger(__name__)

_SENTINEL: Any = object()


class WebUIChannel(BaseChannel):
    """HTTP/SSE channel for the browser-based chat interface."""

    name = "webui"

    def __init__(self, config: WebUIConfig, bus: MessageBus) -> None:
        super().__init__(config, bus)
        self._queues: dict[str, asyncio.Queue] = {}
        self._server = None
        self._app = self._build_app()

    # ------------------------------------------------------------------
    # BaseChannel interface
    # ------------------------------------------------------------------

    async def start(self) -> None:
        import uvicorn

        self._running = True
        port: int = getattr(self.config, "port", 8080)
        config = uvicorn.Config(
            self._app,
            host="0.0.0.0",
            port=port,
            log_level="warning",
            loop="asyncio",
        )
        self._server = uvicorn.Server(config)
        logger.info("WebUI channel starting on port %d", port)
        await self._server.serve()

    async def stop(self) -> None:
        self._running = False
        if self._server is not None:
            self._server.should_exit = True
        for queue in list(self._queues.values()):
            await queue.put(_SENTINEL)
        self._queues.clear()

    async def send(self, msg: OutboundMessage) -> None:
        queue = self._queues.get(msg.chat_id)
        if queue is None:
            return
        is_progress = bool(msg.metadata.get("_progress"))
        event_type = "progress" if is_progress else "final"
        await queue.put({"type": event_type, "message": msg.content})

    # ------------------------------------------------------------------
    # FastAPI app
    # ------------------------------------------------------------------

    def _build_app(self) -> FastAPI:
        app = FastAPI(title="ohmo WebUI API")

        cors_origins: list[str] = list(getattr(self.config, "cors_origins", []))
        if cors_origins:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=cors_origins,
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["*"],
            )

        @app.post("/api/chat", status_code=202)
        async def post_chat(request: Request) -> dict:
            body = await request.json()
            session_id: str = str(body.get("session_id", ""))
            message: str = str(body.get("message", ""))
            await self._handle_message(
                sender_id=session_id,
                chat_id=session_id,
                content=message,
            )
            return {"status": "accepted"}

        @app.get("/api/stream")
        async def get_stream(session_id: str, request: Request) -> StreamingResponse:
            queue: asyncio.Queue = asyncio.Queue()
            self._queues[session_id] = queue

            async def event_generator():
                try:
                    while True:
                        if await request.is_disconnected():
                            break
                        try:
                            event = await asyncio.wait_for(queue.get(), timeout=1.0)
                        except asyncio.TimeoutError:
                            yield ": keepalive\n\n"
                            continue
                        if event is _SENTINEL:
                            break
                        yield f"data: {json.dumps(event)}\n\n"
                finally:
                    self._queues.pop(session_id, None)

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "Connection": "keep-alive",
                },
            )

        @app.get("/api/sessions")
        async def get_sessions() -> dict:
            return {"sessions": list(self._queues.keys())}

        return app
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_channels/test_webui.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/openharness/channels/impl/webui.py tests/test_channels/test_webui.py
git commit -m "feat(channels): implement WebUIChannel with FastAPI SSE server"
```

---

## Task 4: Register WebUIChannel in ChannelManager

**Files:**
- Modify: `src/openharness/channels/impl/manager.py`
- Test: `tests/test_channels/test_webui_manager.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_channels/test_webui_manager.py`:

```python
from openharness.channels.bus.queue import MessageBus
from openharness.channels.impl.manager import ChannelManager
from openharness.channels.impl.webui import WebUIChannel
from openharness.config.schema import Config, WebUIConfig


def test_channel_manager_registers_webui_when_enabled():
    config = Config()
    config.channels.webui = WebUIConfig(enabled=True, port=8080, allow_from=["*"])
    bus = MessageBus()
    manager = ChannelManager(config, bus)
    assert "webui" in manager.channels
    assert isinstance(manager.channels["webui"], WebUIChannel)


def test_channel_manager_skips_webui_when_disabled():
    config = Config()
    config.channels.webui = WebUIConfig(enabled=False)
    bus = MessageBus()
    manager = ChannelManager(config, bus)
    assert "webui" not in manager.channels
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_channels/test_webui_manager.py -v
```

Expected: `FAILED — AssertionError: 'webui' not in manager.channels`

- [ ] **Step 3: Add webui block to ChannelManager._init_channels()**

In `src/openharness/channels/impl/manager.py`, add after the Matrix block (before `self._validate_allow_from()`):

```python
        # WebUI channel
        if self.config.channels.webui.enabled:
            try:
                from openharness.channels.impl.webui import WebUIChannel
                self.channels["webui"] = WebUIChannel(
                    self.config.channels.webui,
                    self.bus,
                )
                logger.info("WebUI channel enabled on port %d", self.config.channels.webui.port)
            except ImportError as e:
                logger.warning("WebUI channel not available: %s", e)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_channels/test_webui_manager.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
pytest tests/test_channels/ tests/test_config/ -v --tb=short
```

Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/openharness/channels/impl/manager.py tests/test_channels/test_webui_manager.py
git commit -m "feat(channels): register WebUIChannel in ChannelManager"
```

---

## Task 5: Update docker-entrypoint.sh for WEBUI_PORT

**Files:**
- Modify: `docker-entrypoint.sh`

- [ ] **Step 1: Update entrypoint to add webui block**

The current entrypoint generates a `gateway.json` with only `telegram` when `OHMO_TELEGRAM_TOKEN` is set. Update it to also add a `webui` channel block when `WEBUI_PORT` is set.

Replace the body of the `if [ -n "$OHMO_TELEGRAM_TOKEN" ]` block in `docker-entrypoint.sh`:

```sh
if [ -n "$OHMO_TELEGRAM_TOKEN" ]; then
    PROVIDER="${OHMO_PROVIDER_PROFILE:-azure-openai}"
    PERMISSION="${OHMO_PERMISSION_MODE:-full_auto}"

    # Build enabled_channels list
    ENABLED_CHANNELS='"telegram"'
    CHANNEL_CONFIGS='"telegram": {
      "allow_from": ["*"],
      "token": "'"$OHMO_TELEGRAM_TOKEN"'",
      "reply_to_message": true
    }'

    if [ -n "$WEBUI_PORT" ]; then
        ENABLED_CHANNELS="$ENABLED_CHANNELS, \"webui\""
        CORS_LIST="[]"
        if [ -n "$WEBUI_CORS_ORIGINS" ]; then
            # Convert comma-separated string to JSON array
            CORS_LIST=$(echo "$WEBUI_CORS_ORIGINS" | awk -F',' '{
                printf "[";
                for(i=1;i<=NF;i++) {
                    gsub(/^ +| +$/, "", $i);
                    printf "\"" $i "\"";
                    if(i<NF) printf ",";
                }
                printf "]"
            }')
        fi
        CHANNEL_CONFIGS="$CHANNEL_CONFIGS,
    \"webui\": {
      \"port\": $WEBUI_PORT,
      \"allow_from\": [\"*\"],
      \"cors_origins\": $CORS_LIST
    }"
    fi

    cat > "$CONFIG_FILE" <<EOF
{
  "provider_profile": "$PROVIDER",
  "enabled_channels": [$ENABLED_CHANNELS],
  "session_routing": "chat-thread",
  "send_progress": true,
  "send_tool_hints": true,
  "permission_mode": "$PERMISSION",
  "sandbox_enabled": false,
  "allow_remote_admin_commands": false,
  "allowed_remote_admin_commands": [],
  "log_level": "${OHMO_LOG_LEVEL:-INFO}",
  "channel_configs": {
    $CHANNEL_CONFIGS
  }
}
EOF
    echo "[entrypoint] wrote $CONFIG_FILE (profile=$PROVIDER permission=$PERMISSION)"
elif [ ! -f "$CONFIG_FILE" ]; then
    echo "[entrypoint] OHMO_TELEGRAM_TOKEN not set and $CONFIG_FILE not found — gateway will start with defaults (no channels enabled)"
fi
```

- [ ] **Step 2: Test locally with docker run**

```bash
# Verify webui block is generated
docker run --rm \
  -e OHMO_TELEGRAM_TOKEN=test-token \
  -e WEBUI_PORT=8080 \
  -e WEBUI_CORS_ORIGINS="http://localhost:5173" \
  $(docker build -q .) \
  cat /data/ohmo/gateway.json
```

Expected: JSON with `"enabled_channels": ["telegram", "webui"]` and a `webui` block with `port: 8080`.

If Docker is not available locally, verify by running the script directly:

```bash
OHMO_TELEGRAM_TOKEN=tok WEBUI_PORT=8080 WEBUI_CORS_ORIGINS="http://localhost:5173" \
  OHMO_WORKSPACE=/tmp/test-ohmo sh docker-entrypoint.sh echo done
cat /tmp/test-ohmo/gateway.json
```

- [ ] **Step 3: Commit**

```bash
git add docker-entrypoint.sh
git commit -m "feat(entrypoint): generate webui channel config when WEBUI_PORT is set"
```

---

## Task 6: Frontend scaffold

**Files:**
- Create: `frontend/web/package.json`
- Create: `frontend/web/vite.config.ts`
- Create: `frontend/web/tsconfig.json`
- Create: `frontend/web/index.html`
- Create: `frontend/web/src/main.tsx`

- [ ] **Step 1: Create package.json**

Create `frontend/web/package.json`:

```json
{
  "name": "@openharness/webui",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.4.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.5.0",
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.1",
    "jsdom": "^25.0.0",
    "msw": "^2.4.0",
    "typescript": "^5.7.3",
    "vite": "^5.4.0",
    "vitest": "^2.1.0"
  }
}
```

- [ ] **Step 2: Create vite.config.ts**

Create `frontend/web/vite.config.ts`:

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const gatewayApiUrl = process.env.VITE_GATEWAY_API_URL ?? 'http://localhost:8080';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: gatewayApiUrl,
        changeOrigin: true,
        // SSE requires no response buffering
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['cache-control'] = 'no-cache';
          });
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
  },
});
```

- [ ] **Step 3: Create tsconfig.json**

Create `frontend/web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Create index.html**

Create `frontend/web/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>ohmo</title>
    <script src="/config.js" onerror="window.GATEWAY_API_URL=undefined"></script>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: Create src/main.tsx**

Create `frontend/web/src/main.tsx`:

```typescript
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './components/App';
import './index.css';

const root = document.getElementById('root');
if (!root) throw new Error('root element not found');

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>
);
```

- [ ] **Step 6: Create src/index.css**

Create `frontend/web/src/index.css`:

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: #0d0d14;
  color: #e2e8f0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 14px;
  height: 100vh;
  overflow: hidden;
}

#root { height: 100vh; display: flex; flex-direction: column; }
```

- [ ] **Step 7: Create Vitest setup file**

Create `frontend/web/src/test/setup.ts`:

```typescript
import '@testing-library/jest-dom';
import { afterEach, beforeAll, afterAll } from 'vitest';
import { cleanup } from '@testing-library/react';
import { server } from './msw-server';

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => { cleanup(); server.resetHandlers(); });
afterAll(() => server.close());
```

Create `frontend/web/src/test/msw-server.ts`:

```typescript
import { setupServer } from 'msw/node';

export const server = setupServer();
```

- [ ] **Step 8: Install dependencies**

```bash
cd /Volumes/ExternalSSD/train/OpenHarness/frontend/web
npm install
```

Expected: `node_modules/` created, no errors.

- [ ] **Step 9: Commit**

```bash
cd /Volumes/ExternalSSD/train/OpenHarness
git add frontend/web/package.json frontend/web/vite.config.ts frontend/web/tsconfig.json \
    frontend/web/index.html frontend/web/src/main.tsx frontend/web/src/index.css \
    frontend/web/src/test/setup.ts frontend/web/src/test/msw-server.ts \
    frontend/web/package-lock.json
git commit -m "feat(webui): scaffold React+Vite+TypeScript frontend"
```

---

## Task 7: types.ts

**Files:**
- Create: `frontend/web/src/types.ts`

- [ ] **Step 1: Create types.ts**

Create `frontend/web/src/types.ts`:

```typescript
export type GatewayEvent = {
  type: 'progress' | 'delta' | 'final' | 'error' | 'ping';
  message?: string;
};

export type Message = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
};

export type SessionInfo = {
  id: string;
  label: string;
  createdAt: number;
};

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';
```

- [ ] **Step 2: Commit**

```bash
git add frontend/web/src/types.ts
git commit -m "feat(webui): add TypeScript types for gateway events and messages"
```

---

## Task 8: useGatewaySession hook

**Files:**
- Create: `frontend/web/src/hooks/useGatewaySession.ts`
- Create: `frontend/web/src/hooks/useGatewaySession.test.ts`

- [ ] **Step 1: Write the failing tests**

> EventSource is not available in JSDOM. The hook accepts an injectable `createEventSource` factory (default: `(url) => new EventSource(url)`) so tests can pass a mock without needing a real server.

Create `frontend/web/src/hooks/useGatewaySession.test.ts`:

```typescript
import { renderHook, act } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { server } from '../test/msw-server';
import { useGatewaySession, type CreateEventSource } from './useGatewaySession';
import { describe, it, expect, vi } from 'vitest';

/** Build a minimal mock EventSource that lets tests fire events synchronously. */
function makeMockEs() {
  const es = {
    onopen: null as ((e: Event) => void) | null,
    onerror: null as ((e: Event) => void) | null,
    onmessage: null as ((e: MessageEvent) => void) | null,
    close: vi.fn(),
    fireOpen() { this.onopen?.(new Event('open')); },
    fireMessage(data: string) {
      this.onmessage?.(new MessageEvent('message', { data }));
    },
    fireError() { this.onerror?.(new Event('error')); },
  };
  return es;
}

type MockEs = ReturnType<typeof makeMockEs>;

describe('useGatewaySession', () => {
  it('starts with empty messages and connecting status', () => {
    const es = makeMockEs();
    const { result } = renderHook(() =>
      useGatewaySession('s1', () => es as unknown as EventSource)
    );
    expect(result.current.messages).toEqual([]);
    expect(result.current.streamingText).toBe('');
    expect(result.current.status).toBe('connecting');
  });

  it('final event commits message to messages array and clears streamingText', () => {
    const es = makeMockEs();
    const { result } = renderHook(() =>
      useGatewaySession('s2', () => es as unknown as EventSource)
    );

    act(() => {
      es.fireOpen();
      es.fireMessage('{"type":"final","message":"Hello agent!"}');
    });

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].role).toBe('assistant');
    expect(result.current.messages[0].text).toBe('Hello agent!');
    expect(result.current.streamingText).toBe('');
    expect(result.current.status).toBe('connected');
  });

  it('send() adds user message optimistically and POSTs to /api/chat', async () => {
    const postSpy = vi.fn();
    server.use(
      http.post('/api/chat', async ({ request }) => {
        postSpy(await request.json());
        return HttpResponse.json({ status: 'accepted' }, { status: 202 });
      })
    );

    const es = makeMockEs();
    const { result } = renderHook(() =>
      useGatewaySession('s3', () => es as unknown as EventSource)
    );

    await act(async () => {
      result.current.send('hello gateway');
      await new Promise(r => setTimeout(r, 50));
    });

    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0].role).toBe('user');
    expect(result.current.messages[0].text).toBe('hello gateway');
    expect(postSpy).toHaveBeenCalledWith({ session_id: 's3', message: 'hello gateway' });
  });

  it('error event sets status to error', () => {
    const es = makeMockEs();
    const { result } = renderHook(() =>
      useGatewaySession('s4', () => es as unknown as EventSource)
    );

    act(() => {
      es.fireMessage('{"type":"error","message":"Auth failed"}');
    });

    expect(result.current.status).toBe('error');
  });
});
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Volumes/ExternalSSD/train/OpenHarness/frontend/web
npm test
```

Expected: `FAIL — Cannot find module './useGatewaySession'`

- [ ] **Step 3: Implement useGatewaySession**

Create `frontend/web/src/hooks/useGatewaySession.ts`:

```typescript
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ConnectionStatus, GatewayEvent, Message } from '../types';

declare global {
  interface Window { GATEWAY_API_URL?: string; }
}

export type CreateEventSource = (url: string) => EventSource;

const GATEWAY_API_URL: string =
  (typeof window !== 'undefined' && window.GATEWAY_API_URL) ||
  (import.meta.env.VITE_GATEWAY_API_URL as string | undefined) ||
  '';

const FLUSH_INTERVAL_MS = 50;
const FLUSH_CHARS = 384;

function makeId(): string {
  return Math.random().toString(36).slice(2);
}

export type UseGatewaySessionReturn = {
  messages: Message[];
  streamingText: string;
  status: ConnectionStatus;
  send: (text: string) => void;
};

const defaultCreateEs: CreateEventSource = (url) => new EventSource(url);

export function useGatewaySession(
  sessionId: string,
  createEventSource: CreateEventSource = defaultCreateEs,
): UseGatewaySessionReturn {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingText, setStreamingText] = useState('');
  const [status, setStatus] = useState<ConnectionStatus>('connecting');

  const pendingDeltaRef = useRef('');
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flushDelta = useCallback(() => {
    const pending = pendingDeltaRef.current;
    if (!pending) return;
    pendingDeltaRef.current = '';
    setStreamingText(prev => prev + pending);
  }, []);

  const commitStreaming = useCallback((finalText: string) => {
    if (flushTimerRef.current) {
      clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    pendingDeltaRef.current = '';
    setStreamingText('');
    setMessages(prev => [...prev, { id: makeId(), role: 'assistant', text: finalText }]);
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    const url = `${GATEWAY_API_URL}/api/stream?session_id=${encodeURIComponent(sessionId)}`;
    const es = createEventSource(url);

    es.onopen = () => setStatus('connected');
    es.onerror = () => setStatus('disconnected');

    es.onmessage = (evt: MessageEvent) => {
      let event: GatewayEvent;
      try { event = JSON.parse(evt.data as string) as GatewayEvent; } catch { return; }

      if (event.type === 'ping') return;

      if (event.type === 'progress') {
        setStatus('connected');
        return;
      }

      if (event.type === 'delta') {
        pendingDeltaRef.current += event.message ?? '';
        if (pendingDeltaRef.current.length >= FLUSH_CHARS) {
          flushDelta();
          return;
        }
        if (!flushTimerRef.current) {
          flushTimerRef.current = setTimeout(() => {
            flushTimerRef.current = null;
            flushDelta();
          }, FLUSH_INTERVAL_MS);
        }
        return;
      }

      if (event.type === 'final') {
        commitStreaming(event.message ?? '');
        setStatus('connected');
        return;
      }

      if (event.type === 'error') {
        setMessages(prev => [
          ...prev,
          { id: makeId(), role: 'assistant', text: `⚠️ ${event.message ?? 'Unknown error'}` },
        ]);
        setStatus('error');
        setStreamingText('');
      }
    };

    return () => {
      es.close();
      if (flushTimerRef.current) {
        clearTimeout(flushTimerRef.current);
        flushTimerRef.current = null;
      }
    };
  }, [sessionId, createEventSource, flushDelta, commitStreaming]);

  const send = useCallback((text: string) => {
    setMessages(prev => [...prev, { id: makeId(), role: 'user', text }]);
    setStatus('connected');
    fetch(`${GATEWAY_API_URL}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message: text }),
    }).catch(() => setStatus('error'));
  }, [sessionId]);

  return { messages, streamingText, status, send };
}
```

- [ ] **Step 4: Run tests**

```bash
cd /Volumes/ExternalSSD/train/OpenHarness/frontend/web
npm test
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
cd /Volumes/ExternalSSD/train/OpenHarness
git add frontend/web/src/types.ts \
    frontend/web/src/hooks/useGatewaySession.ts \
    frontend/web/src/hooks/useGatewaySession.test.ts
git commit -m "feat(webui): implement useGatewaySession hook with SSE streaming"
```

---

## Task 9: React components

**Files:**
- Create: `frontend/web/src/components/StatusBar.tsx`
- Create: `frontend/web/src/components/MessageBubble.tsx`
- Create: `frontend/web/src/components/StreamingBubble.tsx`
- Create: `frontend/web/src/components/ChatPane.tsx`
- Create: `frontend/web/src/components/SessionSidebar.tsx`
- Create: `frontend/web/src/components/App.tsx`
- Create: `frontend/web/src/components/components.css`

- [ ] **Step 1: Create components.css**

Create `frontend/web/src/components/components.css`:

```css
/* Layout */
.app { display: flex; height: 100vh; overflow: hidden; }

/* Sidebar */
.sidebar {
  width: 220px; min-width: 180px; background: #111; border-right: 1px solid #1e2433;
  display: flex; flex-direction: column; padding: 12px 8px;
}
.sidebar-title { font-size: 11px; color: #4a5568; text-transform: uppercase;
  letter-spacing: .08em; padding: 4px 8px 8px; }
.session-item {
  padding: 6px 10px; border-radius: 5px; cursor: pointer; font-size: 12px;
  color: #a0aec0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  transition: background 0.1s;
}
.session-item:hover { background: #1e2433; color: #e2e8f0; }
.session-item.active { background: #1e3a5f; color: #90cdf4; }
.session-item .dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%;
  background: #48bb78; margin-right: 6px; }
.new-chat-btn {
  margin-top: auto; padding: 7px 10px; background: none; border: 1px solid #2d3748;
  border-radius: 5px; color: #4299e1; font-size: 12px; cursor: pointer; text-align: left;
}
.new-chat-btn:hover { background: #1e2433; }

/* Chat pane */
.chat-pane { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

/* Status bar */
.status-bar {
  padding: 4px 16px; font-size: 11px; border-bottom: 1px solid #1e2433;
  display: flex; align-items: center; gap: 6px; color: #4a5568;
}
.status-bar .dot { width: 6px; height: 6px; border-radius: 50%; }
.status-bar.connected .dot { background: #48bb78; }
.status-bar.thinking .dot { background: #ed8936; animation: pulse 1s infinite; }
.status-bar.error .dot { background: #e53e3e; }
.status-bar.disconnected .dot { background: #718096; }
@keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:.3; } }

/* Messages */
.messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 10px; }
.bubble { max-width: 78%; padding: 8px 13px; border-radius: 10px; line-height: 1.5; font-size: 13px; }
.bubble.user { align-self: flex-end; background: #2b4a7a; color: #e2e8f0; }
.bubble.assistant { align-self: flex-start; background: #1e2433; color: #e2e8f0; }
.bubble.streaming { align-self: flex-start; background: #1e2433; color: #e2e8f0; }
.bubble.streaming::after { content: '▋'; animation: blink .7s infinite; }
@keyframes blink { 0%,100% { opacity:1; } 50% { opacity:0; } }

/* Composer */
.composer {
  display: flex; gap: 8px; padding: 12px 16px; border-top: 1px solid #1e2433;
}
.composer textarea {
  flex: 1; background: #1e2433; border: 1px solid #2d3748; border-radius: 6px;
  color: #e2e8f0; font-size: 13px; padding: 8px 10px; resize: none;
  font-family: inherit; outline: none; min-height: 38px; max-height: 120px;
}
.composer textarea:focus { border-color: #4299e1; }
.composer button {
  padding: 8px 14px; background: #2b6cb0; border: none; border-radius: 6px;
  color: #fff; font-size: 13px; cursor: pointer; align-self: flex-end;
}
.composer button:hover { background: #3182ce; }
.composer button:disabled { background: #2d3748; color: #4a5568; cursor: default; }
```

- [ ] **Step 2: Create StatusBar.tsx**

Create `frontend/web/src/components/StatusBar.tsx`:

```typescript
import type { ConnectionStatus } from '../types';

type Props = { status: ConnectionStatus; label?: string };

const STATUS_LABELS: Record<ConnectionStatus, string> = {
  connecting: 'Connecting…',
  connected: 'Connected',
  disconnected: 'Disconnected',
  error: 'Connection error',
};

export function StatusBar({ status, label }: Props) {
  return (
    <div className={`status-bar ${status}`}>
      <span className="dot" />
      <span>{label ?? STATUS_LABELS[status]}</span>
    </div>
  );
}
```

- [ ] **Step 3: Create MessageBubble.tsx**

Create `frontend/web/src/components/MessageBubble.tsx`:

```typescript
import type { Message } from '../types';

export function MessageBubble({ message }: { message: Message }) {
  return (
    <div className={`bubble ${message.role}`}>
      {message.text}
    </div>
  );
}
```

- [ ] **Step 4: Create StreamingBubble.tsx**

Create `frontend/web/src/components/StreamingBubble.tsx`:

```typescript
export function StreamingBubble({ text }: { text: string }) {
  if (!text) return null;
  return <div className="bubble streaming">{text}</div>;
}
```

- [ ] **Step 5: Create ChatPane.tsx**

Create `frontend/web/src/components/ChatPane.tsx`:

```typescript
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';
import type { ConnectionStatus, Message } from '../types';
import { MessageBubble } from './MessageBubble';
import { StreamingBubble } from './StreamingBubble';
import { StatusBar } from './StatusBar';

type Props = {
  messages: Message[];
  streamingText: string;
  status: ConnectionStatus;
  onSend: (text: string) => void;
};

export function ChatPane({ messages, streamingText, status, onSend }: Props) {
  const [draft, setDraft] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const busy = status === 'connected' && streamingText.length > 0;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingText]);

  const submit = useCallback(() => {
    const text = draft.trim();
    if (!text || busy) return;
    setDraft('');
    onSend(text);
  }, [draft, busy, onSend]);

  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }, [submit]);

  return (
    <div className="chat-pane">
      <StatusBar status={status} />
      <div className="messages">
        {messages.map(m => <MessageBubble key={m.id} message={m} />)}
        <StreamingBubble text={streamingText} />
        <div ref={bottomRef} />
      </div>
      <div className="composer">
        <textarea
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
          rows={1}
        />
        <button onClick={submit} disabled={!draft.trim() || busy}>
          Send
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Create SessionSidebar.tsx**

Create `frontend/web/src/components/SessionSidebar.tsx`:

```typescript
import type { SessionInfo } from '../types';

type Props = {
  sessions: SessionInfo[];
  activeId: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  activeSessions: string[];
};

export function SessionSidebar({ sessions, activeId, onSelect, onNew, activeSessions }: Props) {
  return (
    <nav className="sidebar">
      <div className="sidebar-title">Sessions</div>
      {sessions.map(s => (
        <div
          key={s.id}
          className={`session-item${s.id === activeId ? ' active' : ''}`}
          onClick={() => onSelect(s.id)}
        >
          {activeSessions.includes(s.id) && <span className="dot" />}
          {s.label}
        </div>
      ))}
      <button className="new-chat-btn" onClick={onNew}>+ New chat</button>
    </nav>
  );
}
```

- [ ] **Step 7: Create App.tsx**

Create `frontend/web/src/components/App.tsx`:

```typescript
import { useCallback, useEffect, useState } from 'react';
import type { SessionInfo } from '../types';
import { useGatewaySession } from '../hooks/useGatewaySession';
import { SessionSidebar } from './SessionSidebar';
import { ChatPane } from './ChatPane';
import './components.css';

const SESSIONS_KEY = 'ohmo_sessions';
const ACTIVE_KEY = 'ohmo_active_session';

function makeId() { return Math.random().toString(36).slice(2); }
function newSession(): SessionInfo {
  return { id: makeId(), label: `Chat ${new Date().toLocaleTimeString()}`, createdAt: Date.now() };
}

function loadSessions(): SessionInfo[] {
  try { return JSON.parse(localStorage.getItem(SESSIONS_KEY) ?? '[]'); } catch { return []; }
}
function saveSessions(s: SessionInfo[]) { localStorage.setItem(SESSIONS_KEY, JSON.stringify(s)); }

export function App() {
  const [sessions, setSessions] = useState<SessionInfo[]>(() => {
    const s = loadSessions();
    return s.length ? s : [newSession()];
  });
  const [activeId, setActiveId] = useState<string>(
    () => localStorage.getItem(ACTIVE_KEY) ?? sessions[0]?.id ?? ''
  );
  const [serverSessions, setServerSessions] = useState<string[]>([]);

  const { messages, streamingText, status, send } = useGatewaySession(activeId);

  useEffect(() => { saveSessions(sessions); }, [sessions]);
  useEffect(() => { localStorage.setItem(ACTIVE_KEY, activeId); }, [activeId]);

  useEffect(() => {
    const poll = () => {
      fetch('/api/sessions')
        .then(r => r.json())
        .then((d: { sessions: string[] }) => setServerSessions(d.sessions))
        .catch(() => {});
    };
    poll();
    const t = setInterval(poll, 10_000);
    return () => clearInterval(t);
  }, []);

  const handleNew = useCallback(() => {
    const s = newSession();
    setSessions(prev => [s, ...prev]);
    setActiveId(s.id);
  }, []);

  return (
    <div className="app">
      <SessionSidebar
        sessions={sessions}
        activeId={activeId}
        onSelect={setActiveId}
        onNew={handleNew}
        activeSessions={serverSessions}
      />
      <ChatPane
        messages={messages}
        streamingText={streamingText}
        status={status}
        onSend={send}
      />
    </div>
  );
}
```

- [ ] **Step 8: Verify build**

```bash
cd /Volumes/ExternalSSD/train/OpenHarness/frontend/web
npm run build
```

Expected: `dist/` created, no TypeScript errors.

- [ ] **Step 9: Run all frontend tests**

```bash
npm test
```

Expected: all tests pass.

- [ ] **Step 10: Commit**

```bash
cd /Volumes/ExternalSSD/train/OpenHarness
git add frontend/web/src/components/
git commit -m "feat(webui): implement React components (sidebar, chat pane, bubbles)"
```

---

## Task 10: Component tests

**Files:**
- Create: `frontend/web/src/components/SessionSidebar.test.tsx`
- Create: `frontend/web/src/components/MessageBubble.test.tsx`

- [ ] **Step 1: Write SessionSidebar test**

Create `frontend/web/src/components/SessionSidebar.test.tsx`:

```typescript
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { SessionSidebar } from './SessionSidebar';

const sessions = [
  { id: 'a', label: 'Chat A', createdAt: 1 },
  { id: 'b', label: 'Chat B', createdAt: 2 },
];

describe('SessionSidebar', () => {
  it('renders session labels', () => {
    render(<SessionSidebar sessions={sessions} activeId="a" onSelect={vi.fn()} onNew={vi.fn()} activeSessions={[]} />);
    expect(screen.getByText('Chat A')).toBeInTheDocument();
    expect(screen.getByText('Chat B')).toBeInTheDocument();
  });

  it('calls onNew when + New chat is clicked', () => {
    const onNew = vi.fn();
    render(<SessionSidebar sessions={sessions} activeId="a" onSelect={vi.fn()} onNew={onNew} activeSessions={[]} />);
    fireEvent.click(screen.getByText('+ New chat'));
    expect(onNew).toHaveBeenCalledOnce();
  });

  it('marks active session with active class', () => {
    const { container } = render(
      <SessionSidebar sessions={sessions} activeId="b" onSelect={vi.fn()} onNew={vi.fn()} activeSessions={[]} />
    );
    const items = container.querySelectorAll('.session-item');
    expect(items[1]).toHaveClass('active');
  });
});
```

- [ ] **Step 2: Write MessageBubble test**

Create `frontend/web/src/components/MessageBubble.test.tsx`:

```typescript
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MessageBubble } from './MessageBubble';

describe('MessageBubble', () => {
  it('renders user message with user class', () => {
    const { container } = render(<MessageBubble message={{ id: '1', role: 'user', text: 'Hello' }} />);
    expect(container.firstChild).toHaveClass('user');
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });

  it('renders assistant message with assistant class', () => {
    const { container } = render(<MessageBubble message={{ id: '2', role: 'assistant', text: 'Hi there' }} />);
    expect(container.firstChild).toHaveClass('assistant');
  });
});
```

- [ ] **Step 3: Run tests**

```bash
cd /Volumes/ExternalSSD/train/OpenHarness/frontend/web
npm test
```

Expected: all tests pass (including the 4 hook tests + 5 component tests = 9+ total).

- [ ] **Step 4: Commit**

```bash
cd /Volumes/ExternalSSD/train/OpenHarness
git add frontend/web/src/components/SessionSidebar.test.tsx \
    frontend/web/src/components/MessageBubble.test.tsx
git commit -m "test(webui): add component tests for SessionSidebar and MessageBubble"
```

---

## Task 11: Dockerfile and nginx.conf

**Files:**
- Create: `frontend/web/Dockerfile`
- Create: `frontend/web/nginx.conf`

- [ ] **Step 1: Create nginx.conf**

Create `frontend/web/nginx.conf`:

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    # Runtime-inject GATEWAY_API_URL without a rebuild
    location = /config.js {
        add_header Content-Type "application/javascript";
        add_header Cache-Control "no-store";
        return 200 "window.GATEWAY_API_URL='${GATEWAY_API_URL}';";
    }

    # Proxy /api/* to gateway — no CORS needed, same origin for the browser
    location /api/ {
        proxy_pass ${GATEWAY_API_URL}/api/;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        chunked_transfer_encoding on;
        proxy_set_header X-Forwarded-For $remote_addr;
    }

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

> **Note:** `${GATEWAY_API_URL}` is substituted by `envsubst` at container startup (handled by the nginx base image via `docker-entrypoint.d`). Set `GATEWAY_API_URL` as an env var when running the container.

- [ ] **Step 2: Create Dockerfile**

Create `frontend/web/Dockerfile`:

```dockerfile
# --- Build stage ---
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/web/package*.json ./
RUN npm ci
COPY frontend/web/ .
RUN npm run build

# --- Serve stage ---
FROM nginx:alpine
# Remove default config
RUN rm /etc/nginx/conf.d/default.conf
# Copy our config — uses envsubst variables
COPY frontend/web/nginx.conf /etc/nginx/templates/default.conf.template
# Copy built SPA
COPY --from=build /app/dist /usr/share/nginx/html
# nginx alpine image runs envsubst on templates/ at startup automatically
EXPOSE 80
```

- [ ] **Step 3: Test build locally**

```bash
cd /Volumes/ExternalSSD/train/OpenHarness
docker build -f frontend/web/Dockerfile -t ohmo-webui:local .
docker run --rm -p 8081:80 \
  -e GATEWAY_API_URL=http://host.docker.internal:8080 \
  ohmo-webui:local
```

Open `http://localhost:8081` — the SPA should load.

- [ ] **Step 4: Commit**

```bash
git add frontend/web/Dockerfile frontend/web/nginx.conf
git commit -m "feat(webui): add Dockerfile and nginx config for ACA deployment"
```

---

## Task 12: Update deploy.sh

**Files:**
- Modify: `deploy.sh`

- [ ] **Step 1: Add gateway ingress and webui app to deploy.sh**

At the end of `deploy.sh` (after the existing `az containerapp show` check), add:

```bash
# Enable internal ingress on gateway for the WebUI API
echo "Enabling internal ingress on gateway (port 8080)..."
az containerapp ingress enable \
  --name $ACA_APP \
  --resource-group $RG \
  --type internal \
  --target-port 8080 \
  --transport http

GATEWAY_FQDN=$(az containerapp show \
  --name $ACA_APP \
  --resource-group $RG \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)

echo "Gateway internal FQDN: $GATEWAY_FQDN"

# Build and deploy web app
WEBUI_APP="ohmo-webui"
echo "Building web app image..."
az acr build \
  --registry "$ACR" \
  --image ohmo-webui:latest \
  --file frontend/web/Dockerfile \
  .

echo "Deploying web app container..."
az containerapp create \
  --name "$WEBUI_APP" \
  --resource-group "$RG" \
  --environment "$ACA_ENV" \
  --image "$ACR.azurecr.io/ohmo-webui:latest" \
  --registry-server "$ACR.azurecr.io" \
  --registry-identity "$IDENTITY_ID" \
  --cpu 0.25 \
  --memory 0.5Gi \
  --min-replicas 1 \
  --max-replicas 3 \
  --ingress external \
  --target-port 80 \
  --env-vars \
      GATEWAY_API_URL="https://$GATEWAY_FQDN" 2>/dev/null || \
az containerapp update \
  --name "$WEBUI_APP" \
  --resource-group "$RG" \
  --image "$ACR.azurecr.io/ohmo-webui:latest" \
  --set-env-vars \
      GATEWAY_API_URL="https://$GATEWAY_FQDN"

WEBUI_FQDN=$(az containerapp show \
  --name "$WEBUI_APP" \
  --resource-group "$RG" \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)
echo "WebUI available at: https://$WEBUI_FQDN"
```

- [ ] **Step 2: Commit**

```bash
git add deploy.sh
git commit -m "feat(deploy): add gateway internal ingress and ohmo-webui ACA app"
```

---

## Task 13: Update .gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add .superpowers/ to .gitignore**

```bash
echo '.superpowers/' >> /Volumes/ExternalSSD/train/OpenHarness/.gitignore
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore .superpowers/ brainstorm artifacts"
```

---

## Task 14: End-to-end smoke test (local)

- [ ] **Step 1: Start the gateway with webui enabled**

```bash
# Set WEBUI_PORT to enable the channel
WEBUI_PORT=8080 ohmo gateway run
```

Expected log line: `WebUI channel starting on port 8080`

- [ ] **Step 2: Start the React dev server**

```bash
cd /Volumes/ExternalSSD/train/OpenHarness/frontend/web
VITE_GATEWAY_API_URL=http://localhost:8080 npm run dev
```

- [ ] **Step 3: Open browser and test**

Navigate to `http://localhost:5173`.

1. The sidebar shows one session; status bar shows "Connected"
2. Type "hello" and press Enter — user bubble appears immediately
3. After a few seconds — assistant response streams in
4. Click "+ New chat" — a new session entry appears in the sidebar; the chat pane clears

- [ ] **Step 4: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: address issues found in local smoke test"
```

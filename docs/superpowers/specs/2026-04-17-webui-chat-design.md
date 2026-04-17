# WebUI Chat Interface — Design Spec

**Date:** 2026-04-17  
**Status:** Approved  
**Scope:** React+Vite SPA → SSE → WebUIChannel → ohmo gateway → Azure OpenAI

---

## Problem

The ohmo gateway is only reachable via Telegram. Adding a browser-based chat interface lets users interact with the same gateway and agent without a Telegram account, and provides a richer UI for ACA-deployed scenarios.

---

## Architecture

### Flow

```
Browser (React SPA)
  POST /api/chat          → inbound message → bus.inbound
  GET  /api/stream (SSE)  ← outbound events ← bus.outbound
       ↕
  WebUIChannel (FastAPI/Starlette, :8080)
       ↕
  MessageBus → OhmoGatewayBridge → SessionRuntimePool
       ↕
  Azure OpenAI (ManagedIdentityCredential on ACA, DefaultAzureCredential locally)
```

### Local development

```
Browser :5173 (Vite dev server)
    ↕  HTTP + SSE
Gateway :8080 (WebUIChannel embedded in ohmo gateway process)
    ↕
Azure OpenAI  (az login / DefaultAzureCredential)
```

### ACA deployment

```
Browser (anywhere)
    ↓ HTTPS
ohmo-webui  (new ACA app, external ingress :80)
  nginx serves React SPA static files
  /config.js injects GATEWAY_API_URL at runtime
    ↓ HTTP (ACA internal network)
brain-copilot-usi-demo-app  (existing gateway ACA app)
  internal ingress added on :8080
  WebUIChannel API + Telegram polling (both running in same container)
    ↓
Azure OpenAI  (ManagedIdentityCredential, IDENTITY_CLIENT_ID=c9427d44-…)
```

The gateway's **Telegram polling is untouched** — adding internal ingress does not affect the outbound-only Telegram connection.

---

## Backend: WebUIChannel

**File:** `src/openharness/channels/impl/webui.py`

### Class

```python
class WebUIChannel(BaseChannel):
    name = "webui"

    def __init__(self, config: WebUIChannelConfig, bus: MessageBus): ...
    async def start(self) -> None:   # launches Uvicorn on config.port
    async def stop(self) -> None:    # shuts down Uvicorn, drains SSE queues
    async def send(self, msg: OutboundMessage) -> None:  # routes to per-session queue
```

### Config model

```python
@dataclass
class WebUIChannelConfig:
    port: int = 8080
    allow_from: list[str] = field(default_factory=lambda: ["*"])
    cors_origins: list[str] = field(default_factory=list)
```

### HTTP endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/chat` | Submit a message. Body: `{"session_id": str, "message": str}`. Returns 202. |
| `GET` | `/api/stream` | SSE stream. Query: `?session_id=<uuid>`. Streams events until disconnect. |
| `GET` | `/api/sessions` | Returns list of active session IDs (for sidebar). |

`POST /api/chat` calls `_handle_message(sender_id=session_id, chat_id=session_id, content=message)`, which puts an `InboundMessage` on `bus.inbound`. The response arrives asynchronously via the SSE stream, not in the POST response body.

### SSE event schema

All events are JSON objects on the `data:` field of an SSE frame.

```jsonc
{"type": "progress", "message": "🤔 Calling TPM hello..."}   // tool hint / thinking
{"type": "delta",    "message": "Query 1 — Hello"}            // streaming text token
{"type": "final",    "message": "Query 1: Hello World ✓\n…"} // turn complete
{"type": "error",    "message": "Auth failed: ..."}           // error
```

`delta` events use the same 50ms / 384-char buffered-flush pattern as the terminal frontend to avoid excessive re-renders.

### Per-session SSE queue registry

`WebUIChannel` maintains `_queues: dict[str, asyncio.Queue]`:
- Created when a client connects to `/api/stream`
- Populated by `send()` when `OutboundMessage.chat_id` matches a key
- Removed on client disconnect (prevents memory leak for abandoned sessions)
- If `send()` finds no queue for a session (client disconnected), the message is silently dropped

### Session key

```
session_key = f"webui:{session_id}"
```

Computed via `InboundMessage.session_key_override`, which bypasses the default `channel:chat_id` formation. This ensures the WebUI session space is isolated from Telegram sessions.

### gateway.json config

```json
{
  "enabled_channels": ["telegram", "webui"],
  "channel_configs": {
    "webui": {
      "port": 8080,
      "allow_from": ["*"],
      "cors_origins": ["http://localhost:5173"]
    }
  }
}
```

`docker-entrypoint.sh` generates the `webui` block when `WEBUI_PORT` is set. `WEBUI_CORS_ORIGINS` (comma-separated) populates `cors_origins`.

> **CORS scope:** `cors_origins` is only needed for **local dev** when the Vite dev server (`:5173`) calls the gateway (`:8080`) directly. On ACA, nginx proxies `/api/` to the gateway on the same origin — no CORS headers are required and `cors_origins` can be left empty or omitted.

### ChannelManager registration

`src/openharness/channels/impl/manager.py` registers `"webui"` alongside existing channel types:

```python
if adapter_type == "webui":
    channel = WebUIChannel(config=WebUIChannelConfig(**cfg), bus=self.bus)
```

---

## Frontend: React + Vite SPA

**Directory:** `frontend/web/`

### File structure

```
frontend/web/
├── index.html
├── vite.config.ts          # dev proxy: /api → http://localhost:8080 (eliminates CORS in dev)
                            # proxy config: server.proxy['/api'] = { target: VITE_GATEWAY_API_URL,
                            #   changeOrigin: true, ws: false }
├── package.json
└── src/
    ├── main.tsx
    ├── App.tsx              # layout: SessionSidebar (left) + ChatPane (right)
    ├── types.ts             # BackendEvent, TranscriptItem — copied from terminal/
    ├── hooks/
    │   └── useGatewaySession.ts   # SSE + POST, streaming state management
    └── components/
        ├── SessionSidebar.tsx     # session list, new chat button
        ├── ChatPane.tsx           # message list + composer input
        ├── MessageBubble.tsx      # user / assistant bubble, markdown rendering
        ├── StreamingBubble.tsx    # live delta text + progress spinner
        └── StatusBar.tsx          # connected / thinking / error indicator
```

### useGatewaySession hook

```typescript
const { messages, streamingText, status, send } = useGatewaySession(sessionId)
```

**On mount:**
- Opens `new EventSource(`${GATEWAY_API_URL}/api/stream?session_id=${sessionId}`)`
- `delta` → accumulate in `pendingDelta` ref, flush at 50ms / 384 chars → `streamingText`
- `final` → commit `streamingText` to `messages[]`, clear buffer
- `progress` → update `status` label
- `error` → push error message to `messages[]`, stop busy state
- On unmount: close `EventSource`

**send(text):**
1. Append `{role: "user", text}` to `messages[]` immediately (optimistic)
2. `POST /api/chat` `{session_id, message: text}`
3. Set `status = "thinking"`

### Session management

Sessions are persisted in `localStorage`:

```typescript
// keys
"ohmo_sessions"        // JSON array of {id: string, label: string, createdAt: number}
"ohmo_active_session"  // currently selected session ID
```

- On first load: generate a UUID, store as active session
- On refresh: restore active session → same gateway session resumes (gateway holds it in `SessionRuntimePool`)
- "New chat" button: generate new UUID, push to sessions list, switch active
- `GET /api/sessions` polled when sidebar opens — used to mark which sessions the gateway still holds in memory (shows a dot indicator)

### GATEWAY_API_URL

| Environment | Value |
|---|---|
| Local dev | `VITE_GATEWAY_API_URL=http://localhost:8080` (`.env.local`) |
| ACA | `GATEWAY_API_URL` env var in container → injected via nginx `/config.js` |

Vite exposes `import.meta.env.VITE_GATEWAY_API_URL` at build time. For ACA, nginx serves:
```
GET /config.js → "window.GATEWAY_API_URL = 'https://...'"
```
`main.tsx` reads `window.GATEWAY_API_URL ?? import.meta.env.VITE_GATEWAY_API_URL` — the runtime value wins over the build-time default.

---

## ACA Deployment Changes

### brain-copilot-usi-demo-app (existing gateway — modified)

```bash
# Enable internal ingress on port 8080
az containerapp ingress enable \
  --name brain-copilot-usi-demo-app \
  --resource-group rg-copilot-usi-demo \
  --type internal \
  --target-port 8080 \
  --transport http

# Add new env vars
az containerapp update \
  --name brain-copilot-usi-demo-app \
  --resource-group rg-copilot-usi-demo \
  --set-env-vars \
      WEBUI_PORT=8080 \
      WEBUI_CORS_ORIGINS=https://<ohmo-webui-fqdn>
```

Telegram polling is unchanged — no token change, no revision restart required beyond normal deploy cycle.

### ohmo-webui (new ACA app)

```bash
# Build and push via ACR Tasks
az acr build \
  --registry acragentflowdev \
  --image ohmo-webui:latest \
  --file frontend/web/Dockerfile \
  .

# Create container app
az containerapp create \
  --name ohmo-webui \
  --resource-group rg-copilot-usi-demo \
  --environment brain-copilot-usi-demo-env \
  --image acragentflowdev.azurecr.io/ohmo-webui:latest \
  --registry-server acragentflowdev.azurecr.io \
  --registry-identity "$IDENTITY_ID" \
  --cpu 0.25 --memory 0.5Gi \
  --min-replicas 1 --max-replicas 3 \
  --ingress external --target-port 80 \
  --env-vars \
      GATEWAY_API_URL=https://<brain-copilot-usi-demo-app-internal-fqdn>:8080
```

### frontend/web/Dockerfile

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/web/package*.json ./
RUN npm ci
COPY frontend/web/ .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/web/nginx.conf /etc/nginx/conf.d/default.conf
```

### nginx.conf (runtime GATEWAY_API_URL injection)

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;

    location /config.js {
        add_header Content-Type application/javascript;
        return 200 "window.GATEWAY_API_URL='${GATEWAY_API_URL}';";
    }

    location /api/ {
        proxy_pass $GATEWAY_API_URL;
        proxy_set_header Connection '';
        proxy_buffering off;           # required for SSE
        chunked_transfer_encoding on;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

The nginx `/api/` proxy block means the browser never makes a cross-origin request — it always talks to nginx on `:80`, and nginx forwards to the gateway. This eliminates the CORS requirement entirely.

---

## Testing Strategy

### Backend tests — `tests/test_webui_channel.py` (pytest-asyncio + httpx AsyncClient)

| Test | What it verifies |
|---|---|
| `test_post_chat_enqueues_inbound_message` | POST /api/chat → InboundMessage lands on bus.inbound with correct content |
| `test_sse_stream_receives_outbound_message` | Connect SSE → push OutboundMessage via channel.send() → event received |
| `test_disconnect_cleans_up_queue` | Connect SSE → disconnect → queue removed from registry |
| `test_session_key_format` | POST with session_id="abc" → InboundMessage.session_key == "webui:abc" |

### Frontend tests — `frontend/web/src/` (Vitest + MSW)

| Test | What it verifies |
|---|---|
| `useGatewaySession — delta events accumulate into streamingText` | Buffer fills correctly |
| `useGatewaySession — final event commits to messages, clears buffer` | Turn-complete flow |
| `useGatewaySession — send() POSTs and sets status=thinking` | Optimistic UI + fetch call |
| `useGatewaySession — SSE error event shows error message` | Error handling |
| `MessageBubble — renders markdown correctly` | Markdown output |
| `SessionSidebar — new chat creates new session ID` | UUID generation + localStorage |

MSW intercepts `EventSource` and `fetch` — no real server required.

---

## Files Changed

### New
- `src/openharness/channels/impl/webui.py`
- `frontend/web/` (full SPA — index.html, vite.config.ts, package.json, src/)
- `frontend/web/Dockerfile`
- `frontend/web/nginx.conf`
- `tests/test_webui_channel.py`
- `docs/webui-guide.md`

### Modified
- `src/openharness/channels/impl/manager.py` — register `"webui"` channel type
- `docker-entrypoint.sh` — generate webui config block from `WEBUI_PORT` / `WEBUI_CORS_ORIGINS` env vars
- `deploy.sh` — enable internal ingress on gateway, add `ohmo-webui` ACA deploy step
- `.gitignore` — add `.superpowers/`

---

## Out of scope

- Authentication (API key / OAuth) — open for now, can be added to `WebUIChannel.is_allowed()` later
- File/image upload from the web UI
- Multiple simultaneous Telegram bots (separate design)
- WebSocket transport (SSE is sufficient for unidirectional streaming)

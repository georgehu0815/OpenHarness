# WebUI Chat Interface Guide

A browser-based chat interface that connects to the ohmo gateway via SSE, running alongside the existing Telegram integration.

---

## What Changed

### New files
| File | Purpose |
|---|---|
| `src/openharness/channels/impl/webui.py` | `WebUIChannel` — FastAPI/Uvicorn HTTP server embedded in the gateway process |
| `frontend/web/` | React+Vite SPA — sidebar session list + streaming chat pane |
| `frontend/web/Dockerfile` | 2-stage build: Node → nginx static serve |
| `frontend/web/nginx.conf` | SPA routing, `/api/` proxy to gateway, runtime URL injection |
| `tests/test_channels/test_webui.py` | Backend channel tests |
| `tests/test_config/test_webui_config.py` | Config schema tests |

### Modified files
| File | Change |
|---|---|
| `src/openharness/config/schema.py` | Added `WebUIConfig`, registered `webui` field in `ChannelConfigs` |
| `src/openharness/channels/impl/manager.py` | Registers `WebUIChannel` when `channels.webui.enabled = true` |
| `docker-entrypoint.sh` | Generates `"webui"` block in `gateway.json` when `WEBUI_PORT` is set |
| `deploy.sh` | Enables internal ingress on gateway, deploys `ohmo-webui` ACA app |
| `pyproject.toml` | Added `fastapi>=0.115.0`, `uvicorn[standard]>=0.30.0` |

---

## Architecture

```
Browser (React SPA)
  POST /api/chat          → session message → bus.inbound
  GET  /api/stream (SSE)  ← streamed response ← bus.outbound
       ↕
  WebUIChannel (FastAPI on :8080, embedded in gateway process)
       ↕
  MessageBus → OhmoGatewayBridge → SessionRuntimePool
       ↕
  Azure OpenAI
```

SSE events sent to the browser:

```json
{"type": "progress", "message": "🤔 Calling tool..."}
{"type": "delta",    "message": "partial text token"}
{"type": "final",    "message": "complete response text"}
{"type": "error",    "message": "error description"}
```

---

## Running Locally

### Prerequisites

```bash
# Python dependencies (fastapi + uvicorn are now in pyproject.toml)
pip install -e ".[dev]"

# Node dependencies
cd frontend/web && npm install && cd ../..
```

### Step 1 — Start the gateway with WebUI enabled

The gateway needs a `gateway.json` with the `webui` channel enabled. The easiest way is to set `WEBUI_PORT` in the environment and let the entrypoint generate the config, **or** add the channel manually.

**Option A — Environment variable (mirrors ACA behavior)**

```bash
OHMO_TELEGRAM_TOKEN=your-token \
WEBUI_PORT=8080 \
WEBUI_CORS_ORIGINS="http://localhost:5173" \
OHMO_WORKSPACE=/tmp/ohmo-dev \
sh docker-entrypoint.sh ohmo gateway run
```

**Option B — Edit gateway.json directly**

In `~/.ohmo/gateway.json` (or wherever your workspace points), add the webui channel:

```json
{
  "enabled_channels": ["telegram", "webui"],
  "channel_configs": {
    "telegram": {
      "allow_from": ["*"],
      "token": "YOUR_TELEGRAM_TOKEN"
    },
    "webui": {
      "port": 8080,
      "allow_from": ["*"],
      "cors_origins": ["http://localhost:5173"]
    }
  }
}
```

Then start normally:

```bash
ohmo gateway run
```

You should see a log line like:
```
INFO  WebUI channel starting on port 8080
```

### Step 2 — Start the React dev server

```bash
cd frontend/web
VITE_GATEWAY_API_URL=http://localhost:8080 npm run dev
```

The Vite dev server proxies `/api/*` to the gateway, so no CORS issues.

### Step 3 — Open the browser

Navigate to **http://localhost:5173**

- The sidebar shows your sessions (persisted in `localStorage`)
- Type a message and press **Enter** (or **Shift+Enter** for a new line)
- The response streams in token-by-token
- Click **+ New chat** to start a fresh session

---

## Running Tests

### Backend

```bash
pytest tests/test_channels/test_webui.py tests/test_config/test_webui_config.py -v
```

### Frontend

```bash
cd frontend/web
npm test
```

### All backend tests (regression check)

```bash
pytest tests/ -q --timeout=15
```

---

## ACA Deployment

### 1. Update the existing gateway app

Enable internal ingress on port 8080 and add the `WEBUI_PORT` env var so the entrypoint generates the webui config block:

```bash
RG="rg-copilot-usi-demo"
ACA_APP="brain-copilot-usi-demo-app"

az containerapp ingress enable \
  --name $ACA_APP \
  --resource-group $RG \
  --type internal \
  --target-port 8080 \
  --transport http

az containerapp update \
  --name $ACA_APP \
  --resource-group $RG \
  --set-env-vars \
      WEBUI_PORT=8080 \
      WEBUI_CORS_ORIGINS=""   # leave empty — nginx proxy handles it
```

Telegram polling is unchanged — adding internal ingress does not affect the outbound Telegram connection.

### 2. Build and deploy the web app

Run `deploy.sh` — it now handles both steps automatically:

```bash
./deploy.sh
```

Or do it manually:

```bash
ACR="acragentflowdev"
RG="rg-copilot-usi-demo"
ACA_ENV="brain-copilot-usi-demo-env"
IDENTITY_ID="<your-identity-resource-id>"

# Get gateway internal FQDN
GATEWAY_FQDN=$(az containerapp show \
  --name brain-copilot-usi-demo-app \
  --resource-group $RG \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)

# Build the web app image
az acr build \
  --registry $ACR \
  --image ohmo-webui:latest \
  --file frontend/web/Dockerfile \
  .

# Create (or update) the web app container
az containerapp create \
  --name ohmo-webui \
  --resource-group $RG \
  --environment $ACA_ENV \
  --image $ACR.azurecr.io/ohmo-webui:latest \
  --registry-server $ACR.azurecr.io \
  --registry-identity $IDENTITY_ID \
  --cpu 0.25 --memory 0.5Gi \
  --min-replicas 1 --max-replicas 3 \
  --ingress external --target-port 80 \
  --env-vars GATEWAY_API_URL="https://$GATEWAY_FQDN"
```

The web app container runs nginx which:
- Serves the React SPA at `/`
- Injects `GATEWAY_API_URL` at runtime via `/config.js` (no image rebuild needed to change the gateway URL)
- Proxies `/api/*` to the gateway's internal endpoint (browser stays same-origin, no CORS headers needed)

### Updating the gateway URL after deploy

```bash
az containerapp update \
  --name ohmo-webui \
  --resource-group rg-copilot-usi-demo \
  --set-env-vars GATEWAY_API_URL="https://<new-gateway-fqdn>"
```

---

## Configuration Reference

### gateway.json — webui channel options

```json
{
  "channel_configs": {
    "webui": {
      "port": 8080,
      "allow_from": ["*"],
      "cors_origins": ["http://localhost:5173"]
    }
  }
}
```

| Field | Default | Description |
|---|---|---|
| `port` | `8080` | Port the FastAPI/Uvicorn server listens on |
| `allow_from` | `["*"]` | Sender IDs allowed (session UUIDs); `"*"` allows all |
| `cors_origins` | `[]` | Origins allowed for CORS. Only needed for local dev when Vite runs on a different port. Leave empty on ACA (nginx proxy handles it). |

### Environment variables (docker / ACA)

| Variable | Description |
|---|---|
| `WEBUI_PORT` | If set, the entrypoint adds the `webui` channel block to `gateway.json` |
| `WEBUI_CORS_ORIGINS` | Comma-separated CORS origins (e.g. `http://localhost:5173`). Only needed for local dev. |
| `GATEWAY_API_URL` | Set in the web app container. nginx uses this to proxy `/api/` and inject `/config.js`. |
| `VITE_GATEWAY_API_URL` | Set during local `npm run dev` to point the Vite proxy at the gateway. |

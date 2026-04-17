---
title: "ACA WebUI-Gateway Connection Fix: Lessons Learned"
description: Troubleshooting guide for fixing CORS and connectivity issues between the WebUI and Gateway container apps on Azure Container Apps
author: OpenHarness Team
ms.date: 2026-04-17
ms.topic: troubleshooting
---

## Problem Summary

The WebUI container app (`brain-ohmo-webui`) could not connect to the Gateway
container app (`brain-copilot-usi-demo-app`). The browser console showed CORS
errors and `net::ERR_FAILED` when the frontend tried to reach the gateway's
internal FQDN directly.

### Symptoms

* Browser blocked requests to `brain-copilot-usi-demo-app.internal.*.azurecontainerapps.io`
  with "No 'Access-Control-Allow-Origin' header."
* The word `.internal.` in the gateway URL confirmed the browser was trying to
  reach an internal-only endpoint from the public internet — which is
  unreachable by design.
* `/api/sessions`, `/api/chat`, and `/api/stream` all failed.

## Architecture

```text
Browser ──HTTPS──▶ WebUI (nginx, external ingress, port 80)
                      │
                      │  nginx proxy_pass (server-side, same ACA environment)
                      ▼
                   Gateway (FastAPI, internal ingress, port 8080)
```

### Key files

| File | Purpose |
|------|---------|
| `frontend/web/nginx.conf` | Nginx config template — serves the SPA and proxies `/api/*` to the gateway |
| `frontend/web/Dockerfile` | Multi-stage build: Node build → nginx:alpine with envsubst templating |
| `frontend/web/index.html` | SPA entry point — loads `config.js` before the React bundle |
| `frontend/web/src/hooks/useGatewaySession.ts` | React hook — makes all API calls via relative `/api/*` paths |
| `frontend/web/src/components/App.tsx` | Root component — polls `/api/sessions` every 10 seconds |
| `src/openharness/channels/impl/webui.py` | Gateway-side FastAPI server — serves `/api/chat`, `/api/stream`, `/api/sessions` |
| `docker-entrypoint.sh` | Gateway entrypoint — generates `gateway.json` from env vars including CORS config |
| `deploy.sh` | Full deployment script — builds both images and deploys to ACA |
| `rebuild-gateway.sh` | Quick rebuild script — rebuilds and updates only the gateway container |

### How requests flow

1. The browser loads the SPA from `https://brain-ohmo-webui.<env>.azurecontainerapps.io/`.
2. The React app calls relative URLs like `/api/sessions` and `/api/chat`.
3. Nginx matches the `/api/` location block and proxies the request to the
   gateway's internal FQDN via `proxy_pass ${GATEWAY_API_URL}/api/`.
4. The `GATEWAY_API_URL` env var is set to `https://brain-copilot-usi-demo-app.internal.<env>.azurecontainerapps.io`
   and injected at container startup via nginx's `envsubst` templating
   (the file is stored as `/etc/nginx/templates/default.conf.template`).
5. The gateway's FastAPI server processes the request and returns JSON or SSE.
6. Nginx forwards the response back to the browser — same origin, no CORS.

## Root Causes

Two bugs in `frontend/web/nginx.conf` broke this architecture.

### Bug 1 — `config.js` leaked the internal gateway URL

**File:** `frontend/web/nginx.conf`, line 10

The nginx `location = /config.js` block returned:

```javascript
// What the browser received:
window.GATEWAY_API_URL='https://brain-copilot-usi-demo-app.internal...';
```

Even though the current React source (`frontend/web/src/hooks/useGatewaySession.ts`
and `frontend/web/src/components/App.tsx`) uses only relative `/api/*` paths,
the browser loaded this script via `frontend/web/index.html` line 7:

```html
<script src="/config.js" onerror="window.GATEWAY_API_URL=undefined"></script>
```

Cached service workers or older JS bundles could use the value to make direct
requests to the internal URL — bypassing the proxy entirely.

**Fix:** Changed `frontend/web/nginx.conf` line 10 to return `undefined`:

```diff
-        return 200 "window.GATEWAY_API_URL='${GATEWAY_API_URL}';";
+        return 200 "window.GATEWAY_API_URL=undefined;";
```

### Bug 2 — Wrong `Host` header broke ACA virtual-host routing

**File:** `frontend/web/nginx.conf`, line 24 (originally)

The original config forwarded the **webui's hostname** to the gateway:

```nginx
proxy_set_header Host $host;
```

Azure Container Apps uses virtual-host routing — every container app in a
shared environment shares the same IP. ACA inspects the incoming `Host` header
to route traffic to the correct app. When nginx sent `$host` (the webui's
FQDN `brain-ohmo-webui.<env>...`), ACA could not find a matching container app
and returned its generic **404 — "This Container App is stopped or does not
exist"** page.

**Fix:** Changed to `$proxy_host`, which sends the gateway's hostname extracted
from the `proxy_pass` URL:

```diff
-        proxy_set_header Host $host;
+        proxy_set_header Host $proxy_host;
```

### Additional Discovery — ACA `latest` Tag Caching

When using the `:latest` image tag, `az containerapp update` does not force a
re-pull if the tag hasn't changed in ACR's manifest. The deploy appeared
successful but served the old image. Using a **unique tag** (e.g.,
`ohmo-webui:v1776459978`) forced ACA to pull the updated image.

This was diagnosed by checking the running revision:

```bash
az containerapp revision list --name brain-ohmo-webui \
  --resource-group rg-copilot-usi-demo \
  --query "[].{name:name, image:properties.template.containers[0].image}" \
  -o table
```

## Changes Made

### `frontend/web/nginx.conf` — full diff

```diff
diff --git a/frontend/web/nginx.conf b/frontend/web/nginx.conf
--- a/frontend/web/nginx.conf
+++ b/frontend/web/nginx.conf
@@ -7,7 +7,7 @@
     location = /config.js {
         add_header Content-Type "application/javascript";
         add_header Cache-Control "no-store";
-        return 200 "window.GATEWAY_API_URL='${GATEWAY_API_URL}';";
+        return 200 "window.GATEWAY_API_URL=undefined;";
     }

     # Proxy /api/* to gateway — no CORS needed, same origin for the browser
@@ -19,7 +19,16 @@
         proxy_cache off;
         proxy_read_timeout 3600s;
         chunked_transfer_encoding on;
-        proxy_set_header Host $host;
+        # Use gateway's hostname for ACA virtual-host routing
+        proxy_set_header Host $proxy_host;
         proxy_set_header X-Forwarded-For $remote_addr;
+        proxy_set_header X-Forwarded-Proto https;
+        proxy_set_header X-Forwarded-Host $host;
+        proxy_ssl_server_name on;
+        proxy_ssl_verify off;
+        # Safety nets: rewrite any absolute Location header back to relative
+        proxy_redirect ${GATEWAY_API_URL}/ /;
+        proxy_redirect ~^https?://[^/]+/ /;
     }
```

### Summary of all proxy-related directives added

| Directive | Purpose |
|-----------|---------|
| `proxy_set_header Host $proxy_host` | Send the gateway's FQDN so ACA routes to the correct container app |
| `proxy_set_header X-Forwarded-Proto https` | Tell the gateway the original request was HTTPS |
| `proxy_set_header X-Forwarded-Host $host` | Preserve the original webui hostname for logging and link generation |
| `proxy_ssl_server_name on` | Enable SNI when proxying to the HTTPS gateway endpoint |
| `proxy_ssl_verify off` | Skip certificate verification for internal ACA-managed TLS |
| `proxy_redirect ${GATEWAY_API_URL}/ /` | Rewrite any absolute `Location` headers from the gateway back to relative paths |
| `proxy_redirect ~^https?://[^/]+/ /` | Catch-all rewrite for any remaining absolute redirects |

### No other files were changed for this fix

The frontend source (`useGatewaySession.ts`, `App.tsx`) already used relative
paths — no code changes were needed there. The gateway source (`webui.py`)
already had CORS middleware configured, but it was irrelevant to this fix
because the browser never contacts the gateway directly.

## Final Working nginx.conf

```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location = /config.js {
        add_header Content-Type "application/javascript";
        add_header Cache-Control "no-store";
        return 200 "window.GATEWAY_API_URL=undefined;";
    }

    location /api/ {
        proxy_pass ${GATEWAY_API_URL}/api/;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        chunked_transfer_encoding on;
        proxy_set_header Host $proxy_host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Host $host;
        proxy_ssl_server_name on;
        proxy_ssl_verify off;
        proxy_redirect ${GATEWAY_API_URL}/ /;
        proxy_redirect ~^https?://[^/]+/ /;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

## Deployment Commands Used

Build with a unique tag to avoid ACA caching:

```bash
TAG="v$(date +%s)"
az acr build --registry acragentflowdev \
  --image "ohmo-webui:$TAG" \
  --file frontend/web/Dockerfile .
```

Deploy with the unique tag:

```bash
az containerapp update \
  --name brain-ohmo-webui \
  --resource-group rg-copilot-usi-demo \
  --image "acragentflowdev.azurecr.io/ohmo-webui:$TAG"
```

## Verification Steps

1. Confirm `config.js` no longer exposes the gateway URL:

   ```bash
   curl -sS "https://brain-ohmo-webui.redcliff-d11cedef.westus2.azurecontainerapps.io/config.js"
   # Expected: window.GATEWAY_API_URL=undefined;
   ```

2. Confirm the API proxy returns data (not ACA's 404 page):

   ```bash
   curl -sS "https://brain-ohmo-webui.redcliff-d11cedef.westus2.azurecontainerapps.io/api/sessions"
   # Expected: {"sessions":[]}
   ```

3. Open the browser, hard-refresh (`Cmd+Shift+R`), and verify the console is
   free of CORS errors.

4. Check which revision is active and receiving traffic:

   ```bash
   az containerapp revision list --name brain-ohmo-webui \
     --resource-group rg-copilot-usi-demo \
     --query "[].{name:name, active:properties.active, trafficWeight:properties.trafficWeight}" \
     -o table
   ```

## Suggestions Moving Forward

### Use unique image tags instead of `latest`

Tag every build with a commit SHA or timestamp. This eliminates ACA caching
issues and provides clear traceability:

```bash
TAG="$(git rev-parse --short HEAD)-$(date +%s)"
az acr build --registry "$ACR" --image "ohmo-webui:$TAG" ...
az containerapp update --image "$ACR.azurecr.io/ohmo-webui:$TAG" ...
```

### Remove `config.js` entirely

The `config.js` endpoint in `frontend/web/nginx.conf` and the `<script>` tag
in `frontend/web/index.html` line 7 were originally meant to inject a runtime
API URL for the frontend. Since the architecture mandates that all API calls go
through the nginx reverse proxy (relative paths), this endpoint serves no
purpose. Consider removing both to avoid confusion:

* Delete the `location = /config.js { ... }` block from `frontend/web/nginx.conf`
* Remove `<script src="/config.js" ...>` from `frontend/web/index.html`

### Add a health-check endpoint

Add a `/api/health` endpoint to `src/openharness/channels/impl/webui.py` and
configure ACA health probes. This helps ACA detect failed containers and
provides a quick smoke test after deployments:

```bash
curl -sS "https://brain-ohmo-webui.redcliff-d11cedef.westus2.azurecontainerapps.io/api/health"
```

### Consider switching gateway to allow insecure internal traffic

The gateway currently requires HTTPS even for internal traffic (`allowInsecure: false`),
which forces nginx to perform TLS to the backend (`proxy_ssl_server_name on`).
Since internal ACA traffic stays within the environment's private network, you
could enable insecure traffic and simplify the proxy:

```bash
az containerapp ingress enable \
  --name brain-copilot-usi-demo-app \
  --resource-group rg-copilot-usi-demo \
  --type internal \
  --target-port 8080 \
  --transport http \
  --allow-insecure
```

Then change `GATEWAY_API_URL` to `http://` and remove the `proxy_ssl_*`
directives from `frontend/web/nginx.conf`.

### Keep the deploy script idempotent

The current `deploy.sh` uses `create || update` patterns which work, but can
mask errors. Consider checking whether resources exist before choosing
create vs. update, and always propagate exit codes.

### Document the architecture

Add the architecture diagram from this guide to the project README. This helps
new contributors understand why requests must stay same-origin and why the
gateway must remain internal-only.

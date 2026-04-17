# WebUI ACA Deployment Guide

## Do I need to redeploy the gateway?

**Yes — one-time changes only.** The gateway image must be rebuilt because:

1. `webui.py` is new code that didn't exist in the previously deployed image
2. `fastapi` and `uvicorn` are new dependencies added to `pyproject.toml`
3. The gateway needs `WEBUI_PORT=8080` env var so the entrypoint generates the webui config block
4. The gateway needs **internal ingress** enabled on port 8080 (was disabled before)

After this first deployment these are permanent — future gateway deploys need no extra steps.

---

## What gets deployed

```
ACA Environment: brain-copilot-usi-demo-env
│
├── brain-copilot-usi-demo-app   (existing gateway — rebuilt + reconfigured)
│     Telegram polling + WebUI API on :8080
│     ingress: internal (new)
│
└── ohmo-webui                   (new app)
      nginx serves React SPA on :80
      ingress: external (HTTPS)
      proxies /api/ → gateway internal FQDN
```

---

## Full deployment (first time)

Run from the repo root:

```bash
./deploy.sh
```

`deploy.sh` does everything in order:
1. Builds the gateway image (includes new `webui.py` + fastapi)
2. Updates the gateway container app (new image + `WEBUI_PORT` env var)
3. Enables internal ingress on the gateway at port 8080
4. Builds the web app image (`frontend/web/Dockerfile`)
5. Creates (or updates) the `ohmo-webui` container app
6. Prints the public URL

At the end you'll see:
```
WebUI available at: https://ohmo-webui.<hash>.westus2.azurecontainerapps.io
```

---

## Step-by-step (manual)

If you prefer to run steps individually:

### Step 1 — Rebuild and update the gateway

```bash
ACR="acragentflowdev"
RG="rg-copilot-usi-demo"
ACA_APP="brain-copilot-usi-demo-app"
IDENTITY_CLIENT_ID="c9427d44-98e2-406a-9527-f7fa7059f984"
TELEGRAM_TOKEN=$(jq -r '.channel_configs.telegram.token' ~/.ohmo/gateway.json)
AOAI_ENDPOINT=$(grep -m 1 'base_url:' ~/.hermes/config.yaml | awk '{print $2}' | tr -d '\n')

# Build new image (includes webui.py + fastapi)
az acr build --registry $ACR --image ohmo-gateway:latest .

# Update the running container with new image + WEBUI_PORT
az containerapp update \
  --name $ACA_APP \
  --resource-group $RG \
  --image $ACR.azurecr.io/ohmo-gateway:latest \
  --set-env-vars \
      OHMO_TELEGRAM_TOKEN=secretref:telegram-token \
      ENDPOINT_URL=secretref:aoai-endpoint \
      AZURE_CLIENT_ID="$IDENTITY_CLIENT_ID" \
      OHMO_PROVIDER_PROFILE=azure-openai \
      OPENHARNESS_ACTIVE_PROFILE=azure-openai \
      OHMO_PERMISSION_MODE=full_auto \
      OHMO_LOG_LEVEL=INFO \
      WEBUI_PORT=8080
```

### Step 2 — Enable internal ingress on the gateway

This opens port 8080 on the internal ACA network so `ohmo-webui` can reach the WebUI API. Telegram is unaffected — it uses outbound polling, not ingress.

```bash
az containerapp ingress enable \
  --name $ACA_APP \
  --resource-group $RG \
  --type internal \
  --target-port 8080 \
  --transport http
```

Get the internal FQDN for the next step:

```bash
GATEWAY_FQDN=$(az containerapp show \
  --name $ACA_APP \
  --resource-group $RG \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)
echo $GATEWAY_FQDN
```

### Step 3 — Build and deploy the web app

```bash
ACA_ENV="brain-copilot-usi-demo-env"
IDENTITY_ID="/subscriptions/ad54c4fb-f585-4033-9e5a-b119d74480b0/resourceGroups/rg-copilot-usi-demo/providers/Microsoft.ManagedIdentity/userAssignedIdentities/copilot-ua-mi"
WEBUI_APP="ohmo-webui"

# Build the nginx+React image
az acr build \
  --registry $ACR \
  --image ohmo-webui:latest \
  --file frontend/web/Dockerfile \
  .

# Create the container app (or update if it already exists)
az containerapp create \
  --name $WEBUI_APP \
  --resource-group $RG \
  --environment $ACA_ENV \
  --image $ACR.azurecr.io/ohmo-webui:latest \
  --registry-server $ACR.azurecr.io \
  --registry-identity $IDENTITY_ID \
  --cpu 0.25 \
  --memory 0.5Gi \
  --min-replicas 1 \
  --max-replicas 3 \
  --ingress external \
  --target-port 80 \
  --env-vars \
      GATEWAY_API_URL="https://$GATEWAY_FQDN" 2>/dev/null || \
az containerapp update \
  --name $WEBUI_APP \
  --resource-group $RG \
  --image $ACR.azurecr.io/ohmo-webui:latest \
  --set-env-vars \
      GATEWAY_API_URL="https://$GATEWAY_FQDN"
```

### Step 4 — Get the public URL

```bash
az containerapp show \
  --name ohmo-webui \
  --resource-group rg-copilot-usi-demo \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv
```

Open `https://<fqdn>` in a browser.

---

## Subsequent deploys (after first time)

### Gateway updated (code changes)

```bash
az acr build --registry acragentflowdev --image ohmo-gateway:latest .
az containerapp update \
  --name brain-copilot-usi-demo-app \
  --resource-group rg-copilot-usi-demo \
  --image acragentflowdev.azurecr.io/ohmo-gateway:latest
```

Internal ingress and `WEBUI_PORT` are already set — no need to touch them again.

### Web app updated (UI changes)

```bash
az acr build \
  --registry acragentflowdev \
  --image ohmo-webui:latest \
  --file frontend/web/Dockerfile \
  .
az containerapp update \
  --name ohmo-webui \
  --resource-group rg-copilot-usi-demo \
  --image acragentflowdev.azurecr.io/ohmo-webui:latest
```

`GATEWAY_API_URL` is already set — no need to change it.

### Change the gateway URL (if gateway FQDN changes)

```bash
GATEWAY_FQDN=$(az containerapp show \
  --name brain-copilot-usi-demo-app \
  --resource-group rg-copilot-usi-demo \
  --query "properties.configuration.ingress.fqdn" --output tsv)

az containerapp update \
  --name ohmo-webui \
  --resource-group rg-copilot-usi-demo \
  --set-env-vars GATEWAY_API_URL="https://$GATEWAY_FQDN"
```

nginx picks up the new URL on restart — no image rebuild needed.

---

## Verify deployment

```bash
# Gateway is running
az containerapp show \
  --name brain-copilot-usi-demo-app \
  --resource-group rg-copilot-usi-demo \
  --query "properties.runningStatus" --output tsv

# Web app is running
az containerapp show \
  --name ohmo-webui \
  --resource-group rg-copilot-usi-demo \
  --query "properties.runningStatus" --output tsv

# Check gateway logs for WebUI startup line
az containerapp logs show \
  --name brain-copilot-usi-demo-app \
  --resource-group rg-copilot-usi-demo \
  --tail 50 | grep -i webui
```

You should see: `INFO  WebUI channel enabled on port 8080`

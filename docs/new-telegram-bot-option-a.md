# Option A — Second Independent Telegram Bot via a New Container App

Deploy a second `brain-copilot-usi-demo-app`-style Container App running the
same gateway image but with its own Telegram token. The existing app is
**completely untouched**.

Each app has:
- Its own Telegram polling loop (no conflict)
- Its own session pool and conversation memory
- Its own managed identity binding (shared identity, isolated runtime)
- Independent log streams and scaling settings

---

## Architecture

```
Telegram Bot A  →  brain-copilot-usi-demo-app   (existing, untouched)
                      └── ACA revision, sessions/, gateway.json

Telegram Bot B  →  brain-copilot-usi-demo-app-2  (new)
                      └── ACA revision, sessions/, gateway.json
```

Both apps pull the same image from `acragentflowdev` and authenticate to
Azure OpenAI with the same user-assigned managed identity.

---

## Prerequisites

- Azure CLI logged in: `az login`
- The existing app is healthy (confirm: `az containerapp show --name brain-copilot-usi-demo-app --resource-group rg-copilot-usi-demo --query "properties.runningStatus" -o tsv`)
- New Telegram bot token from [@BotFather](https://t.me/BotFather) (see [new-telegram-bot.md §Step 1](new-telegram-bot.md))

---

## Step 1 — Set shell variables

```bash
# Shared infrastructure (unchanged)
RG="rg-copilot-usi-demo"
ACA_ENV="brain-copilot-usi-demo-env"
ACR="acragentflowdev"
IDENTITY_ID="/subscriptions/ad54c4fb-f585-4033-9e5a-b119d74480b0/resourceGroups/rg-copilot-usi-demo/providers/Microsoft.ManagedIdentity/userAssignedIdentities/copilot-ua-mi"
IDENTITY_CLIENT_ID="c9427d44-98e2-406a-9527-f7fa7059f984"

# New app
ACA_APP_2="brain-copilot-usi-demo-app-2"       # choose any unique name
NEW_TELEGRAM_TOKEN="<token-from-BotFather>"

# Re-use the same Azure OpenAI endpoint as the existing app
AOAI_ENDPOINT=$(az containerapp secret list \
  --name brain-copilot-usi-demo-app \
  --resource-group "$RG" \
  --query "[?name=='aoai-endpoint'].value" \
  --output tsv 2>/dev/null || echo "<your-aoai-endpoint>")
```

> **Tip:** if you can't read the secret value via CLI, find it in the
> Azure Portal → Container Apps → `brain-copilot-usi-demo-app` →
> Secrets, then copy the `aoai-endpoint` value.

---

## Step 2 — Create secrets for the new app

```bash
# First create the app shell (secrets must exist before env vars reference them)
az containerapp create \
  --name "$ACA_APP_2" \
  --resource-group "$RG" \
  --environment "$ACA_ENV" \
  --image "$ACR.azurecr.io/ohmo-gateway:latest" \
  --registry-server "$ACR.azurecr.io" \
  --registry-identity "$IDENTITY_ID" \
  --cpu 0.5 \
  --memory 1.0Gi \
  --min-replicas 1 \
  --max-replicas 1 \
  --ingress disabled \
  --user-assigned "$IDENTITY_ID" \
  --secrets \
      telegram-token="$NEW_TELEGRAM_TOKEN" \
      aoai-endpoint="$AOAI_ENDPOINT" \
  --env-vars \
      OHMO_TELEGRAM_TOKEN=secretref:telegram-token \
      ENDPOINT_URL=secretref:aoai-endpoint \
      IDENTITY_CLIENT_ID="$IDENTITY_CLIENT_ID" \
      OHMO_PROVIDER_PROFILE=azure-openai \
      OPENHARNESS_ACTIVE_PROFILE=azure-openai \
      OHMO_PERMISSION_MODE=full_auto \
      OHMO_LOG_LEVEL=INFO
```

**Why `--ingress disabled`?**  
The Telegram integration uses long-polling — the container reaches out to
Telegram's servers. No inbound HTTP endpoint is needed.

**Why `--max-replicas 1`?**  
Session state is in-memory. Multiple replicas would split sessions across
instances. Add a persistent volume (see §Optional) before scaling past 1.

---

## Step 3 — Verify the new app starts cleanly

```bash
# Stream logs for the new app only
az containerapp logs show \
  --name "$ACA_APP_2" \
  --resource-group "$RG" \
  --follow
```

Expected startup sequence:

```
[entrypoint] OHMO_TELEGRAM_TOKEN is set — writing /data/ohmo/gateway.json
[entrypoint] wrote /data/ohmo/gateway.json (profile=azure-openai permission=full_auto)
INFO  Telegram bot @<new_bot_username> connected
```

### Confirm running status

```bash
az containerapp show \
  --name "$ACA_APP_2" \
  --resource-group "$RG" \
  --query "properties.runningStatus" \
  --output tsv
# Expected: Running
```

---

## Step 4 — Test both bots independently

Open Telegram and send a message to each bot:

| Bot | App | Expected |
|---|---|---|
| Old bot (`@existing_bot`) | `brain-copilot-usi-demo-app` | Responds as before, unchanged |
| New bot (`@new_bot`) | `brain-copilot-usi-demo-app-2` | Responds independently, fresh session |

The two apps do **not** share session history or memory — each starts with a
clean slate.

---

## Optional — Persistent session storage for the new app

Without a volume, sessions for `app-2` are lost on container restart. Mount an
Azure File Share to persist them:

```bash
STORAGE_ACCOUNT="ohmostorev2$RANDOM"   # must be globally unique

az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RG" \
  --location westus2 \
  --sku Standard_LRS

az storage share-rm create \
  --resource-group "$RG" \
  --storage-account "$STORAGE_ACCOUNT" \
  --name ohmo-workspace-2 \
  --quota 5

STORAGE_KEY=$(az storage account keys list \
  --account-name "$STORAGE_ACCOUNT" \
  --resource-group "$RG" \
  --query "[0].value" --output tsv)

az containerapp env storage set \
  --name "$ACA_ENV" \
  --resource-group "$RG" \
  --storage-name ohmo-workspace-2 \
  --azure-file-account-name "$STORAGE_ACCOUNT" \
  --azure-file-account-key "$STORAGE_KEY" \
  --azure-file-share-name ohmo-workspace-2 \
  --access-mode ReadWrite

az containerapp update \
  --name "$ACA_APP_2" \
  --resource-group "$RG" \
  --volume-mount "storage-name=ohmo-workspace-2,volume-name=ohmo-workspace-2,mount-path=/data/ohmo"
```

---

## Tradeoffs vs Option B

| | Option A (this guide) | Option B (multi-channel gateway) |
|---|---|---|
| Code changes | None | Yes — gateway + config model |
| Isolation | Full (separate process, memory, sessions) | Shared process, shared session pool |
| Cost | 2× compute (0.5 vCPU × 2) | 1× compute |
| Operational complexity | 2 apps to update/redeploy | 1 app, more complex config |
| Failure blast radius | One bot down does not affect the other | Gateway crash takes both bots offline |
| Shared agent memory | No | Yes (same session pool) |

---

## Teardown

```bash
az containerapp delete \
  --name "$ACA_APP_2" \
  --resource-group "$RG" \
  --yes
```

The existing `brain-copilot-usi-demo-app` is unaffected.

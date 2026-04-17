# Adding a New Telegram Bot to the ACA Deployment

This guide walks you through creating a fresh Telegram bot and wiring it to the
already-running **`brain-copilot-usi-demo-app`** Container App — no code changes
or image rebuild required.

---

## Overview

```
You (BotFather) → new bot token
         │
         ▼
  ACA secret  ←  az containerapp secret set
         │
         ▼
  OHMO_TELEGRAM_TOKEN env var  ←  az containerapp update
         │
         ▼
  docker-entrypoint.sh generates /data/ohmo/gateway.json
         │
         ▼
  ohmo gateway polls Telegram → your new bot responds
```

The gateway reads `OHMO_TELEGRAM_TOKEN` at container startup and builds
`gateway.json` automatically. Swapping the token means updating the ACA secret,
pointing the env var at it, and restarting the revision.

---

## Step 1 — Create the bot with @BotFather

1. Open Telegram and start a chat with **[@BotFather](https://t.me/BotFather)**.
2. Send `/newbot` and follow the prompts:
   - **Name** — display name shown in Telegram (e.g. `USI Copilot`)
   - **Username** — must end in `bot` (e.g. `usicopliot_bot`)
3. BotFather replies with a token like:

   ```
   8753298417:AAEu5KuOq...
   ```

4. Copy the token — you will need it in the next step.

> **One gateway process per token.** If the old bot (token `8753298417:…`) is
> still set on ACA, stop the old revision before the new one starts, or update
> the token in a single `az containerapp update` call so only one revision runs
> at a time.

---

## Step 2 — Set shell variables

```bash
RG="rg-copilot-usi-demo"
ACA_APP="brain-copilot-usi-demo-app"

NEW_TOKEN="<paste-token-from-BotFather>"
```

---

## Step 3 — Store the token as an ACA secret

ACA secrets are **immutable** — you cannot edit an existing one in place.
Add a new versioned secret (e.g. `telegram-token-v2`):

```bash
az containerapp secret set \
  --name "$ACA_APP" \
  --resource-group "$RG" \
  --secrets telegram-token-v2="$NEW_TOKEN"
```

**Why a new name?**  
ACA will reject `--secrets telegram-token="…"` if the secret already exists.
Using a version suffix (`-v2`, `-v3`, …) is the standard pattern. The old secret
stays in place and can be removed later once the new bot is confirmed working.

---

## Step 4 — Update the env var to reference the new secret

```bash
az containerapp update \
  --name "$ACA_APP" \
  --resource-group "$RG" \
  --set-env-vars OHMO_TELEGRAM_TOKEN=secretref:telegram-token-v2
```

This change triggers a **new revision** automatically. ACA drains the old
revision and starts a new container that reads the updated env var at startup.

> The managed identity (`IDENTITY_CLIENT_ID=c9427d44-98e2-406a-9527-f7fa7059f984`)
> and all other env vars (`ENDPOINT_URL`, `OPENHARNESS_ACTIVE_PROFILE`, etc.) are
> unchanged — only the Telegram token is updated.

---

## Step 5 — Verify the deployment

### Stream live logs

```bash
az containerapp logs show \
  --name "$ACA_APP" \
  --resource-group "$RG" \
  --follow
```

A healthy startup shows lines like:

```
[entrypoint] OHMO_TELEGRAM_TOKEN is set — writing /data/ohmo/gateway.json
[entrypoint] wrote /data/ohmo/gateway.json (profile=azure-openai permission=full_auto)
INFO  [openharness.channels.impl.telegram] Telegram bot @usicopliot_bot connected
```

If you see `Conflict: terminated by other getUpdates request`, the old revision
is still running against the same token. Wait 30 seconds for ACA to complete the
revision drain, then check again.

### Confirm running status

```bash
az containerapp show \
  --name "$ACA_APP" \
  --resource-group "$RG" \
  --query "properties.runningStatus" \
  --output tsv
# Expected: Running
```

### Confirm the active revision is using the new secret

```bash
az containerapp revision list \
  --name "$ACA_APP" \
  --resource-group "$RG" \
  --query "[?properties.active==\`true\`].{name:name, created:properties.createdTime}" \
  --output table
```

---

## Step 6 — Send a test message

1. Open Telegram and search for your bot's username (e.g. `@usicopliot_bot`).
2. Send `/start` or any message.
3. The bot should respond within a few seconds with the agent's greeting.

For a more diagnostic test:

```
hello
```

or, if the `tpm` skill is wired:

```
tpm hello
```

---

## Step 7 — Restrict access (optional but recommended)

By default `allow_from: ["*"]` lets any Telegram user chat with the bot.
To limit to specific users, find their Telegram user IDs and set them via
a gateway config update.

The simplest way is to add `OHMO_ALLOW_FROM` (if the entrypoint supports it),
or redeploy with a custom `gateway.json` mounted as a volume. For a quick
one-user restriction, the entrypoint-generated config can be overridden by
mounting a pre-written `gateway.json` on an Azure File Share at `/data/ohmo/`:

```json
{
  "provider_profile": "azure-openai",
  "enabled_channels": ["telegram"],
  "permission_mode": "full_auto",
  "channel_configs": {
    "telegram": {
      "token": "<not-used-here-env-var-takes-precedence>",
      "allow_from": ["123456789", "987654321"],
      "reply_to_message": true
    }
  }
}
```

> To find a Telegram user ID, have the user message the bot, then check the
> gateway logs — the `sender_id` field in `InboundMessage` is their numeric ID.

---

## Step 8 — Clean up the old secret (optional)

Once the new bot is confirmed working, remove the stale secret:

```bash
az containerapp secret remove \
  --name "$ACA_APP" \
  --resource-group "$RG" \
  --secret-names telegram-token
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Conflict: terminated by other getUpdates request` | Two processes polling same token | Wait for old revision to drain; check `az containerapp revision list` |
| Bot receives message but does not reply | Auth failure against Azure OpenAI | Check logs for `401`; managed identity role may need a few minutes to propagate |
| `OHMO_TELEGRAM_TOKEN is not set` in logs | Secret reference is wrong | Verify secret name: `az containerapp show --name $ACA_APP --resource-group $RG --query "properties.configuration.secrets"` |
| `Invalid non-printable ASCII character` in logs | Token has a trailing newline | Re-set the secret: `az containerapp secret set --secrets telegram-token-v2="$(echo -n $NEW_TOKEN)"` |
| Bot online but `tpm` commands return 401 | Managed identity not authorised for Fabric | Ensure `IDENTITY_CLIENT_ID` is set and the identity has access to the Fabric workspace |

---

## Resource reference

| Resource | Value |
|---|---|
| Subscription | `ad54c4fb-f585-4033-9e5a-b119d74480b0` |
| Resource group | `rg-copilot-usi-demo` |
| Container App | `brain-copilot-usi-demo-app` |
| Managed identity client ID | `c9427d44-98e2-406a-9527-f7fa7059f984` |
| ACR | `acragentflowdev.azurecr.io` |

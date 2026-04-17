# Deploying ohmo Gateway to Azure Container Apps

This guide walks through building the ohmo gateway Docker image, pushing it to Azure Container Registry, and running it as an Azure Container App connected to Telegram.

## Prerequisites

- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) (`az`) installed and logged in
- Docker installed locally (only needed if you build locally; ACR Tasks can skip this)
- An Azure subscription with:
  - A resource group
  - An Azure OpenAI resource with a deployment (e.g. `gpt-4o-mini`)
  - An Azure Container Registry (ACR)
  - A Container Apps Environment
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

```bash
# Log in to Azure
az login

# Log in to the container registry
az acr login --name acragentflowdev

az account set --subscription "<your-subscription-id>"
```

---

## 1. Set shell variables

Set these once at the start of your terminal session. All commands below reference them.

```bash
# Azure resource names
RG="rg-copilot-usi-demo"                 # resource group
LOCATION="eastus"                        # Azure region
ACR="acragentflowdev"                    # Azure Container Registry name
ACA_ENV="ohmo-env"                       # Container Apps environment name
ACA_APP="ohmo-gateway"                   # Container App name
AOAI_RESOURCE="<your-aoai-name>"         # Azure OpenAI resource name

# User-assigned managed identity (pre-existing — used for both ACR pull and Azure OpenAI)
IDENTITY_CLIENT_ID="c9427d44-98e2-406a-9527-f7fa7059f984"
IDENTITY_PRINCIPAL_ID="2a414bcb-0176-4732-af84-bfd1affbc827"

# ohmo config
TELEGRAM_TOKEN="<your-bot-token>"        # from @BotFather
AOAI_ENDPOINT="https://<your-aoai-name>.openai.azure.com/"
AOAI_DEPLOYMENT="gpt-4o-mini"            # deployment name inside your Azure OpenAI resource
```

---

## 2. Create Azure resources (skip if they already exist)

```bash
# Resource group
az group create --name $RG --location $LOCATION

# Azure Container Registry
az acr create --name $ACR --resource-group $RG --sku Basic --admin-enabled false

# Container Apps environment (consumption plan — pay per use)
az containerapp env create \
  --name $ACA_ENV \
  --resource-group $RG \
  --location $LOCATION
```

---

## 3. Build and push the Docker image

### Verify ACR connectivity first

Before pushing the real image, confirm your Docker credentials reach `acragentflowdev`:

```bash
az acr login --name acragentflowdev

# Pull a public test image and re-tag it into your registry
docker pull mcr.microsoft.com/mcr/hello-world
docker tag  mcr.microsoft.com/mcr/hello-world acragentflowdev.azurecr.io/samples/hello-world

docker push acragentflowdev.azurecr.io/samples/hello-world
# Expected: "latest: digest: sha256:... size: ..."
```

If the push succeeds, your ACR credentials are working and you're ready to push the gateway image.

### Option A — Build in ACR (no local Docker required, fastest)

```bash
cd /path/to/OpenHarness

az acr build \
  --registry acragentflowdev \
  --image ohmo-gateway:latest \
  .
```

### Option B — Build locally then push

```bash
cd /path/to/OpenHarness

docker build -t ohmo-gateway:local .

az acr login --name acragentflowdev
docker tag ohmo-gateway:local acragentflowdev.azurecr.io/ohmo-gateway:latest
docker push acragentflowdev.azurecr.io/ohmo-gateway:latest
```

---

## 4. Pre-flight: grant the identity access to ACR

The user-assigned managed identity needs `AcrPull` on the registry so ACA can pull the image without admin credentials.

```bash
# Look up the identity resource ID by clientId
IDENTITY_ID=$(az identity list \
  --query "[?clientId=='$IDENTITY_CLIENT_ID'].id" \
  --output tsv)

# Grant AcrPull
ACR_ID=$(az acr show \
  --name acragentflowdev \
  --resource-group $RG \
  --query id \
  --output tsv)

az role assignment create \
  --assignee-object-id "$IDENTITY_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role AcrPull \
  --scope "$ACR_ID"
```

---

## 5. Deploy the Container App

The gateway polls Telegram over outbound HTTPS — no inbound port is needed.
`--min-replicas 1` keeps one instance always running so messages are received immediately.

`AZURE_CLIENT_ID` tells `DefaultAzureCredential` which user-assigned identity to use inside the container.

```bash
az containerapp create \
  --name $ACA_APP \
  --resource-group $RG \
  --environment $ACA_ENV \
  --image acragentflowdev.azurecr.io/ohmo-gateway:latest \
  --registry-server acragentflowdev.azurecr.io \
  --registry-identity "$IDENTITY_ID" \
  --cpu 0.5 \
  --memory 1.0Gi \
  --min-replicas 1 \
  --max-replicas 1 \
  --ingress disabled \
  --user-assigned "$IDENTITY_ID" \
  --secrets \
      telegram-token="$TELEGRAM_TOKEN" \
      aoai-endpoint="$AOAI_ENDPOINT" \
  --env-vars \
      OHMO_TELEGRAM_TOKEN=secretref:telegram-token \
      ENDPOINT_URL=secretref:aoai-endpoint \
      AZURE_CLIENT_ID="$IDENTITY_CLIENT_ID" \
      OHMO_PROVIDER_PROFILE=azure-openai \
      OPENHARNESS_ACTIVE_PROFILE=azure-openai \
      OHMO_PERMISSION_MODE=full_auto \
      OHMO_LOG_LEVEL=INFO
```

> **Why `--ingress disabled`?** The Telegram integration uses long-polling (the bot reaches out to Telegram's servers). No inbound HTTP listener is needed, which simplifies the deployment and reduces attack surface.

> **Why `--max-replicas 1`?** The gateway maintains per-chat session state in memory. Running more than one replica would split sessions across instances. Use a persistent volume (see §8) before scaling beyond 1.

---

## 6. Grant the Managed Identity access to Azure OpenAI

`DefaultAzureCredential` inside the container reads `AZURE_CLIENT_ID` and authenticates as the user-assigned managed identity. The identity needs `Cognitive Services OpenAI User` on the Azure OpenAI resource.

```bash
# Get the Azure OpenAI resource ID
AOAI_ID=$(az cognitiveservices account show \
  --name $AOAI_RESOURCE \
  --resource-group $RG \
  --query id \
  --output tsv)

# Assign the role using the known principal ID — no lookup needed
az role assignment create \
  --assignee-object-id "$IDENTITY_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Cognitive Services OpenAI User" \
  --scope "$AOAI_ID"
```

> Role assignments can take 1–2 minutes to propagate. If the first request fails with a 401, wait and retry.

### Local development

Locally, do **not** set `AZURE_CLIENT_ID`. `DefaultAzureCredential` falls through to `AzureCliCredential` and uses your `az login` session automatically — no managed identity or environment variables needed.

```bash
az login   # one-time; refreshes automatically
# ENDPOINT_URL still needs to be set in your local .env
```

---

## 7. Verify the deployment

### Stream live logs

```bash
az containerapp logs show \
  --name $ACA_APP \
  --resource-group $RG \
  --follow
```

A healthy startup looks like:

```
[entrypoint] wrote /data/ohmo/gateway.json (profile=azure-openai permission=full_auto)
2026-04-15 ... [openharness.channels.impl.telegram] INFO Telegram bot @<botname> connected
```

### Check app status

```bash
az containerapp show \
  --name $ACA_APP \
  --resource-group $RG \
  --query "properties.runningStatus" \
  --output tsv
# Expected: Running
```

### Send a test message

Open Telegram, start a chat with your bot, and send:

```
tpm hello --dry-run
```

The bot should respond within a few seconds.

---

## 8. Persistent session storage (optional but recommended)

By default, sessions are stored inside the container and lost on restart.
Mount an Azure File Share to preserve chat history across restarts and redeployments.

```bash
# Create a storage account and file share
STORAGE_ACCOUNT="ohmostore$RANDOM"   # must be globally unique, lowercase, 3–24 chars
az storage account create \
  --name $STORAGE_ACCOUNT \
  --resource-group $RG \
  --location $LOCATION \
  --sku Standard_LRS

az storage share-rm create \
  --resource-group $RG \
  --storage-account $STORAGE_ACCOUNT \
  --name ohmo-workspace \
  --quota 5

STORAGE_KEY=$(az storage account keys list \
  --account-name $STORAGE_ACCOUNT \
  --resource-group $RG \
  --query "[0].value" \
  --output tsv)

# Link the storage to the Container Apps environment
az containerapp env storage set \
  --name $ACA_ENV \
  --resource-group $RG \
  --storage-name ohmo-workspace \
  --azure-file-account-name $STORAGE_ACCOUNT \
  --azure-file-account-key "$STORAGE_KEY" \
  --azure-file-share-name ohmo-workspace \
  --access-mode ReadWrite

# Update the app to mount the share at /data/ohmo
az containerapp update \
  --name $ACA_APP \
  --resource-group $RG \
  --volume-mount "storage-name=ohmo-workspace,volume-name=ohmo-workspace,mount-path=/data/ohmo"
```

---

## 9. Update the image after code changes

```bash
# Rebuild and push
az acr build --registry acragentflowdev --image ohmo-gateway:latest .

# Trigger a new revision
az containerapp update \
  --name $ACA_APP \
  --resource-group $RG \
  --image acragentflowdev.azurecr.io/ohmo-gateway:latest
```

Container Apps creates a new revision and drains the old one automatically.

---

## 10. Update secrets or env vars

Secrets cannot be edited in place — add a new secret with a different name, then update the env var reference.

```bash
# Example: rotate the Telegram token
az containerapp secret set \
  --name $ACA_APP \
  --resource-group $RG \
  --secrets telegram-token-v2="<new-token>"

az containerapp update \
  --name $ACA_APP \
  --resource-group $RG \
  --set-env-vars OHMO_TELEGRAM_TOKEN=secretref:telegram-token-v2
```

---

## 11. Tear down

```bash
az containerapp delete --name $ACA_APP --resource-group $RG --yes
az containerapp env delete --name $ACA_ENV --resource-group $RG --yes
az acr delete --name $ACR --resource-group $RG --yes
az group delete --name $RG --yes   # deletes everything in the group
```

---

## Environment variable reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `OHMO_TELEGRAM_TOKEN` | Yes | — | Telegram bot token from @BotFather. Triggers gateway.json generation. |
| `ENDPOINT_URL` | Yes (Azure OpenAI) | — | Azure OpenAI endpoint URL. |
| `AZURE_CLIENT_ID` | Yes (ACA) | — | Client ID of the user-assigned managed identity. Tells `DefaultAzureCredential` which identity to use. **Omit for local dev** — `az login` is used instead. |
| `OPENHARNESS_ACTIVE_PROFILE` | Yes | `claude-api` | Provider profile to activate. Use `azure-openai`. |
| `OHMO_PROVIDER_PROFILE` | No | `azure-openai` | Written into the generated gateway.json. |
| `OHMO_PERMISSION_MODE` | No | `full_auto` | Tool permission mode. `full_auto` allows all tools without prompts. |
| `OHMO_LOG_LEVEL` | No | `INFO` | Log verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `OHMO_WORKSPACE` | No | `/data/ohmo` | Workspace root inside the container. |

---

## Troubleshooting

**Bot doesn't respond**
- Check logs: `az containerapp logs show --name $ACA_APP --resource-group $RG`
- Confirm `Telegram bot @<name> connected` appears in the logs
- Verify `OHMO_TELEGRAM_TOKEN` is set correctly: `az containerapp show --name $ACA_APP --resource-group $RG --query "properties.configuration.secrets"`

**`DefaultAzureCredential: no credential found`**
- The managed identity role assignment hasn't propagated yet — wait 2 minutes and restart the revision: `az containerapp revision restart --name $ACA_APP --resource-group $RG --revision $(az containerapp revision list --name $ACA_APP --resource-group $RG --query "[0].name" -o tsv)`

**`ENDPOINT_URL environment variable is required`**
- The `ENDPOINT_URL` env var is not reaching the container. Verify: `az containerapp show --name $ACA_APP --resource-group $RG --query "properties.template.containers[0].env"`

**`I'm blocked until you approve the tool prompt`**
- This means a prior session has a conversation history where tools were denied. Clear it:
  ```bash
  # Find and delete the stale session pointer (safe — individual session archives are kept)
  az containerapp exec --name $ACA_APP --resource-group $RG \
    --command "find /data/ohmo/sessions -name 'latest-*.json' -delete"
  ```
  Then restart the revision to clear in-memory sessions.

**Out of memory / OOMKilled**
- Increase memory: `az containerapp update --name $ACA_APP --resource-group $RG --memory 2.0Gi`

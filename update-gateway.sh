#!/usr/bin/env bash
set -euo pipefail

# Rebuild and redeploy the gateway container app only.
# Assumes the app was already created by deploy.sh; this is the fast
# inner-loop script for iterating on gateway code. Config, env vars,
# and secrets are kept aligned with deploy.sh (the source of truth).

# -- Azure auth check --
if ! az account show --query id -o tsv &>/dev/null; then
  echo "ERROR: Not logged in to Azure. Run: az login"
  exit 1
fi

# -- Read secrets from host config (mirrors deploy.sh) --
TELEGRAM_TOKEN=$(jq -r '.channel_configs.telegram.token' ~/.ohmo/gateway.json)
AOAI_ENDPOINT=$(grep -m 1 'base_url:' ~/.hermes/config.yaml | awk '{print $2}' | tr -d '\n')

echo "Updating ohmo gateway on Azure Container Apps..."

# -- Stage host skills into build context (mirrors deploy.sh) --
SKILLS_SRC="${HOME}/.openharness/skills"
SKILLS_STAGE="$(pwd)/skills"

echo "Staging skills from $SKILLS_SRC..."
rm -rf "$SKILLS_STAGE"
if [ -d "$SKILLS_SRC" ]; then
    cp -r "$SKILLS_SRC" "$SKILLS_STAGE"
    echo "  Staged: $(ls "$SKILLS_STAGE" | tr '\n' ' ')"
else
    mkdir -p "$SKILLS_STAGE"
    echo "  No skills found at $SKILLS_SRC — building with empty skills/"
fi

# -- Stage tpm CLI into build context (mirrors deploy.sh) --
TPM_SRC="/Users/ghu/work/CatalystDataLakeAgent/Demo_FabricDataAgent_TPM"
TPM_STAGE="$(pwd)/tpm"

echo "Staging tpm CLI from $TPM_SRC..."
rm -rf "$TPM_STAGE"
if [ -d "$TPM_SRC" ]; then
    mkdir -p "$TPM_STAGE"
    cp "$TPM_SRC/tpm_cli.py" "$TPM_STAGE/"
    cp "$TPM_SRC/requirements.txt" "$TPM_STAGE/"
    cp -r "$TPM_SRC/src" "$TPM_STAGE/"
    cp -r "$TPM_SRC/prompts" "$TPM_STAGE/"
    cp "$TPM_SRC/.vscode/mcp.json" "$TPM_STAGE/"
    echo "  Staged tpm_cli.py + src/ + prompts/ + mcp.json"
else
    echo "  WARNING: tpm source not found at $TPM_SRC — tpm will not be installed"
    mkdir -p "$TPM_STAGE"
    echo "requests>=2.28.0" > "$TPM_STAGE/requirements.txt"
fi

# -- Build gateway image --
ACR="acragentflowdev"
TAG="$(git rev-parse --short HEAD 2>/dev/null || echo dev)-$(date +%s)"
echo "Building gateway image with tag: $TAG"
az acr build --registry "$ACR" --image "ohmo-gateway:$TAG" .

# Clean up staging dirs so they don't leak into the next build
rm -rf "$SKILLS_STAGE" "$TPM_STAGE"
echo "Cleaned up staging directories"

# -- Shared vars (must match deploy.sh) --
RG="rg-copilot-usi-demo"
ACA_ENV="brain-copilot-usi-demo-env"
ACA_APP="brain-copilot-usi-demo-app"
WEBUI_APP="brain-ohmo-webui"
IDENTITY_CLIENT_ID="c9427d44-98e2-406a-9527-f7fa7059f984"

# Recompute webui CORS origin from the ACA environment default domain
ENV_FQDN=$(az containerapp env show --name "$ACA_ENV" --resource-group "$RG" --query "properties.defaultDomain" --output tsv)
WEBUI_CORS_ORIGIN="https://${WEBUI_APP}.${ENV_FQDN}"
echo "WebUI CORS origin: $WEBUI_CORS_ORIGIN"

# -- Refresh secrets (secrets may have rotated on the host) --
az containerapp secret set \
  --name $ACA_APP \
  --resource-group $RG \
  --secrets \
      telegram-token="$TELEGRAM_TOKEN" \
      aoai-endpoint="$AOAI_ENDPOINT"

# -- Roll the new image + re-assert full env var set from deploy.sh --
az containerapp update \
  --name $ACA_APP \
  --resource-group $RG \
  --image "$ACR.azurecr.io/ohmo-gateway:$TAG" \
  --set-env-vars \
      OHMO_TELEGRAM_TOKEN=secretref:telegram-token \
      ENDPOINT_URL=secretref:aoai-endpoint \
      AZURE_CLIENT_ID="$IDENTITY_CLIENT_ID" \
      OHMO_PROVIDER_PROFILE=azure-openai \
      OPENHARNESS_ACTIVE_PROFILE=azure-openai \
      OHMO_PERMISSION_MODE=full_auto \
      OHMO_LOG_LEVEL=INFO \
      WEBUI_PORT=8080 \
      WEBUI_CORS_ORIGINS="$WEBUI_CORS_ORIGIN"

# -- Status --
az containerapp show \
  --name $ACA_APP \
  --resource-group $RG \
  --query "properties.runningStatus" \
  --output tsv

#!/usr/bin/env bash
set -euo pipefail

# Verify Azure CLI is authenticated
if ! az account show --query id -o tsv &>/dev/null; then
  echo "ERROR: Not logged in to Azure. Run: az login"
  exit 1
fi

# Read secrets from host configuration
TELEGRAM_TOKEN=$(jq -r '.channel_configs.telegram.token' ~/.ohmo/gateway.json)
AOAI_ENDPOINT=$(grep -m 1 'base_url:' ~/.hermes/config.yaml | awk '{print $2}' | tr -d '\n')
echo "Deploying ohmo gateway to Azure Container Apps..."

# -- Stage host skills into build context, build image, then clean up --
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



# -- Stage tpm CLI into build context -------------------------------------
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

ACR="acragentflowdev"
TAG="$(git rev-parse --short HEAD 2>/dev/null || echo dev)-$(date +%s)"
echo "Building images with tag: $TAG"
az acr build --registry "$ACR" --image "ohmo-gateway:$TAG" .

rm -rf "$SKILLS_STAGE" "$TPM_STAGE"
echo "Cleaned up staging directories"

# Shared variables
RG="rg-copilot-usi-demo"
LOCATION="westus2"
ACA_ENV="brain-copilot-usi-demo-env"
ACA_APP="brain-copilot-usi-demo-app"
WEBUI_APP="brain-ohmo-webui"
IDENTITY_ID="/subscriptions/ad54c4fb-f585-4033-9e5a-b119d74480b0/resourceGroups/rg-copilot-usi-demo/providers/Microsoft.ManagedIdentity/userAssignedIdentities/copilot-ua-mi"
IDENTITY_CLIENT_ID="c9427d44-98e2-406a-9527-f7fa7059f984"
LAW_NAME="copilot-law"

# Compute webui CORS origin from ACA environment default domain
ENV_FQDN=$(az containerapp env show --name "$ACA_ENV" --resource-group "$RG" --query "properties.defaultDomain" --output tsv)
WEBUI_CORS_ORIGIN="https://${WEBUI_APP}.${ENV_FQDN}"
echo "WebUI CORS origin: $WEBUI_CORS_ORIGIN"
# LOG_ANALYTICS_WORKSPACE_ID=$(az monitor log-analytics workspace show --resource-group $RG --workspace-name $LAW_NAME --query customerId -o tsv)
# LOG_ANALYTICS_KEY=$(az monitor log-analytics workspace get-shared-keys --resource-group $RG --workspace-name $LAW_NAME --query primarySharedKey -o tsv)

# Create Container App Environment
# az containerapp env create \
#   --name $ACA_ENV \
#   --resource-group $RG \
#   --location $LOCATION \
#   --logs-workspace-id "$LOG_ANALYTICS_WORKSPACE_ID" \
#   --logs-workspace-key "$LOG_ANALYTICS_KEY"

# Assign user-assigned identity to the environment
# az containerapp env identity assign \
#   --name $ACA_ENV \
#   --resource-group $RG \
#   --user-assigned "$IDENTITY_ID"


# Deploy gateway (create on first run; secret-set + update on subsequent runs)
echo "Deploying gateway container..."
az containerapp create \
  --name $ACA_APP \
  --resource-group $RG \
  --environment $ACA_ENV \
  --image "$ACR.azurecr.io/ohmo-gateway:$TAG" \
  --registry-server $ACR.azurecr.io \
  --registry-identity $IDENTITY_ID \
  --user-assigned $IDENTITY_ID \
  --cpu 0.5 \
  --memory 1.0Gi \
  --min-replicas 1 \
  --max-replicas 1 \
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
      OHMO_LOG_LEVEL=INFO \
      WEBUI_PORT=8080 \
      WEBUI_CORS_ORIGINS="$WEBUI_CORS_ORIGIN" 2>/dev/null || {
  az containerapp identity assign \
    --name $ACA_APP \
    --resource-group $RG \
    --user-assigned $IDENTITY_ID
  az containerapp secret set \
    --name $ACA_APP \
    --resource-group $RG \
    --secrets \
        telegram-token="$TELEGRAM_TOKEN" \
        aoai-endpoint="$AOAI_ENDPOINT"
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
}

# check status
az containerapp show \
  --name $ACA_APP \
  --resource-group $RG \
  --query "properties.runningStatus" \
  --output tsv

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
echo "Building web app image..."
az acr build \
  --registry "$ACR" \
  --image "ohmo-webui:$TAG" \
  --file frontend/web/Dockerfile \
  .

echo "Deploying web app container..."
az containerapp create \
  --name "$WEBUI_APP" \
  --resource-group "$RG" \
  --environment "$ACA_ENV" \
  --image "$ACR.azurecr.io/ohmo-webui:$TAG" \
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
  --image "$ACR.azurecr.io/ohmo-webui:$TAG" \
  --set-env-vars \
      GATEWAY_API_URL="https://$GATEWAY_FQDN"

WEBUI_FQDN=$(az containerapp show \
  --name "$WEBUI_APP" \
  --resource-group "$RG" \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)
echo "WebUI available at: https://$WEBUI_FQDN"

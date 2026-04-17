#!/usr/bin/env bash
set -euo pipefail

# Rebuild and redeploy the webui container app only.
# Assumes the app was already created by deploy.sh; this is the fast
# inner-loop script for iterating on the frontend. Config and env vars
# are kept aligned with deploy.sh (the source of truth).

# -- Azure auth check --
if ! az account show --query id -o tsv &>/dev/null; then
  echo "ERROR: Not logged in to Azure. Run: az login"
  exit 1
fi

# -- Shared vars (must match deploy.sh) --
ACR="acragentflowdev"
RG="rg-copilot-usi-demo"
ACA_APP="brain-copilot-usi-demo-app"
WEBUI_APP="brain-ohmo-webui"

# -- Build webui image --
TAG="$(git rev-parse --short HEAD 2>/dev/null || echo dev)-$(date +%s)"
echo "Building webui image with tag: $TAG"
az acr build \
  --registry "$ACR" \
  --image "ohmo-webui:$TAG" \
  --file frontend/web/Dockerfile \
  .

# -- Re-fetch gateway internal FQDN so nginx proxy target stays correct --
GATEWAY_FQDN=$(az containerapp show \
  --name "$ACA_APP" \
  --resource-group "$RG" \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)
echo "Gateway internal FQDN: $GATEWAY_FQDN"

# -- Roll the new image + re-assert env var set from deploy.sh --
az containerapp update \
  --name "$WEBUI_APP" \
  --resource-group "$RG" \
  --image "$ACR.azurecr.io/ohmo-webui:$TAG" \
  --set-env-vars \
      GATEWAY_API_URL="https://$GATEWAY_FQDN"

# -- Report the public URL --
WEBUI_FQDN=$(az containerapp show \
  --name "$WEBUI_APP" \
  --resource-group "$RG" \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)
echo "WebUI available at: https://$WEBUI_FQDN"

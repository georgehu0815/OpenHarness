ACR="acragentflowdev"
RG="rg-copilot-usi-demo"
ACA_ENV="brain-copilot-usi-demo-env"
ACA_APP="brain-copilot-usi-demo-app"
WEBUI_APP="brain-ohmo-webui"
IDENTITY_CLIENT_ID="c9427d44-98e2-406a-9527-f7fa7059f984"
TELEGRAM_TOKEN=$(jq -r '.channel_configs.telegram.token' ~/.ohmo/gateway.json)
AOAI_ENDPOINT=$(grep -m 1 'base_url:' ~/.hermes/config.yaml | awk '{print $2}' | tr -d '\n')
TAG="$(git rev-parse --short HEAD 2>/dev/null || echo dev)-$(date +%s)"
echo "Building with tag: $TAG"

# Compute webui CORS origin from environment default domain
ENV_FQDN=$(az containerapp env show --name "$ACA_ENV" --resource-group "$RG" --query "properties.defaultDomain" --output tsv)
WEBUI_CORS_ORIGIN="https://${WEBUI_APP}.${ENV_FQDN}"
echo "WebUI CORS origin: $WEBUI_CORS_ORIGIN"

# Build new image (includes webui.py + fastapi)
az acr build --registry $ACR --image "ohmo-gateway:$TAG" .

# Update the running container with new image + WEBUI_PORT + CORS origin
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
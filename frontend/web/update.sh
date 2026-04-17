az acr build \
  --registry acragentflowdev \
  --image ohmo-webui:latest \
  --file frontend/web/Dockerfile \
  .

az containerapp update \
  --name brain-ohmo-webui \
  --resource-group rg-copilot-usi-demo \
  --image acragentflowdev.azurecr.io/ohmo-webui:latest

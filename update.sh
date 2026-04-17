# az acr build \
#   --registry acragentflowdev \
#   --image ohmo-gateway:latest \
#   .

az containerapp update \
  --name brain-copilot-usi-demo-app \
  --resource-group rg-copilot-usi-demo \
  --image acragentflowdev.azurecr.io/ohmo-gateway:latest



  

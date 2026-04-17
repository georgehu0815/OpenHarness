# Shared variables
RG="rg-copilot-usi-demo"
LOCATION="westus2"
ACA_ENV="brain-copilot-usi-demo-env"
ACA_APP="brain-copilot-usi-demo-app"
az containerapp delete --name $ACA_APP --resource-group $RG --yes
# az containerapp env delete --name $ACA_ENV --resource-group $RG --yes
# az acr delete --name $ACR --resource-group $RG --yes
# az group delete --name $RG --yes   # deletes everything in the group
#!/usr/bin/env bash
set -euo pipefail

SKILLS_SRC="${HOME}/.openharness/skills"
TPM_SRC="/Users/ghu/work/CatalystDataLakeAgent/Demo_FabricDataAgent_TPM"

# Stage host skills into build context (gitignored — must be copied before every build)
rm -rf skills
if [ -d "$SKILLS_SRC" ]; then
    cp -r "$SKILLS_SRC" skills
else
    mkdir -p skills
fi

# Stage tpm CLI into build context (gitignored — must be copied before every build)
rm -rf tpm
mkdir -p tpm
cp "$TPM_SRC/tpm_cli.py"        tpm/
cp "$TPM_SRC/requirements.txt"  tpm/
cp -r "$TPM_SRC/src"            tpm/
cp -r "$TPM_SRC/prompts"        tpm/
cp "$TPM_SRC/.vscode/mcp.json"  tpm/

az acr build \
  --registry acragentflowdev \
  --image ohmo-gateway:latest \
  .

# Clean up staged files
# rm -rf skills tpm


az containerapp update \
  --name brain-copilot-usi-demo-app \
  --resource-group rg-copilot-usi-demo \
  --image acragentflowdev.azurecr.io/ohmo-gateway:latest
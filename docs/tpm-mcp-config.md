# TPM MCP Configuration for Docker Builds

The `tpm` CLI connects to the Fabric Data Agent over HTTP-MCP. Its server endpoint is read from `.vscode/mcp.json` at runtime. Because this file is gitignored, it must be staged into the build context before every Docker build.

---

## How it works

```
build.sh / deploy.sh
  └── stages .vscode/mcp.json → tpm/mcp.json  (flattened, avoids dotdir issues)

Dockerfile
  └── COPY tpm/ /opt/tpm/
        └── /opt/tpm/mcp.json  ← config lands here

tpm_cli.py (at runtime)
  └── imports src/config.py
        └── reads /opt/tpm/mcp.json
```

`src/config.py:41` resolves the path as `Path(__file__).parent.parent / "mcp.json"`, which is `/opt/tpm/mcp.json` inside the container. The source lives under `.vscode/` on the host (VS Code convention) but is staged flat to avoid dot-directory filtering by `az acr build`.

---

## Config file

**Source (host):** `/Users/ghu/work/CatalystDataLakeAgent/Demo_FabricDataAgent_TPM/.vscode/mcp.json`

**In container:** `/opt/tpm/mcp.json`

```json
{
  "servers": {
    "missionControlMcpServer": {
      "url": "https://mcv3-mcp.azurewebsites.net/",
      "type": "http"
    },
    "Fabric TPM Diagnostics Agent MCP server": {
      "type": "http",
      "url": "https://msitapi.fabric.microsoft.com/v1/mcp/workspaces/73e2916f-2924-4875-9492-1d041db069e0/dataagents/e82dca62-4758-48c5-a940-78a357b6044f/agent",
      "headers": { "Content-Type": "application/json" }
    }
  },
  "inputs": []
}
```

`tpm` scenario commands use `"Fabric TPM Diagnostics Agent MCP server"` by default (the `server_name` argument in `load_mcp_config()`).

---

## Staging flow in build.sh / deploy.sh

Both scripts copy the `.vscode/` directory as part of the tpm staging block:

```bash
TPM_SRC="/Users/ghu/work/CatalystDataLakeAgent/Demo_FabricDataAgent_TPM"

rm -rf tpm
mkdir -p tpm
cp "$TPM_SRC/tpm_cli.py"        tpm/
cp "$TPM_SRC/requirements.txt"  tpm/
cp -r "$TPM_SRC/src"            tpm/
cp -r "$TPM_SRC/prompts"        tpm/
cp "$TPM_SRC/.vscode/mcp.json"  tpm/            # ← staged flat (avoids dotdir filtering)
```

The `tpm/` directory is gitignored and cleaned up after each build. It only exists during the `az acr build` step.

---

## Updating the MCP server URL

Edit the source file on the host; the new URL is picked up on the next build automatically:

```bash
# Edit the config
code /Users/ghu/work/CatalystDataLakeAgent/Demo_FabricDataAgent_TPM/.vscode/mcp.json

# Rebuild and redeploy
./build.sh
```

Do **not** edit `tpm/.vscode/mcp.json` directly — that directory is regenerated from scratch on every build.

---

## Troubleshooting

**`FileNotFoundError: /opt/tpm/mcp.json`**

The config was not staged before the build. Verify the staging block ran and check the ACR build log for `COPY tpm/`:

```bash
# Confirm the file exists in the build context before az acr build runs:
ls tpm/mcp.json
```

If the file is missing, check that `TPM_SRC` in `build.sh` points to a valid checkout of the TPM repo.

**`KeyError: 'Fabric TPM Diagnostics Agent MCP server' not found`**

The server name in `mcp.json` was changed or the wrong config file was staged. The key must match exactly:

```bash
python3 -c "import json; d=json.load(open('/opt/tpm/.vscode/mcp.json')); print(list(d['servers'].keys()))"
```

**`tpm hello` returns auth errors (401 / 403)**

The MCP server uses `DefaultAzureCredential` for the Fabric endpoint. Inside ACA, `AZURE_CLIENT_ID` must be set and the managed identity must have access to the Fabric workspace. Auth failures are not config-file issues — the endpoint URL in `mcp.json` is correct if the server name resolves without `KeyError`.

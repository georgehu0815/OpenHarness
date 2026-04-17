"""Configuration loader for MCP server settings.

Reads MCP endpoint URL and headers from .vscode/mcp.json.
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""

    name: str
    url: str
    server_type: str = "http"
    headers: Dict[str, str] = field(default_factory=dict)


def load_mcp_config(
    config_path: Optional[Path] = None,
    server_name: str = "Fabric TPM Diagnostics Agent MCP server",
) -> MCPServerConfig:
    """Load MCP server configuration from .vscode/mcp.json.

    Args:
        config_path: Path to the mcp.json file.  Defaults to
            <project_root>/.vscode/mcp.json.
        server_name: Key of the server entry to load.

    Returns:
        MCPServerConfig with the endpoint details.

    Raises:
        FileNotFoundError: If the config file does not exist.
        KeyError: If the requested server name is not found.
    """
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / "mcp.json"

    with open(config_path, "r", encoding="utf-8") as fh:
        # mcp.json may contain JSONC (comments) — strip them
        raw = fh.read()
        # Simple comment stripping: remove lines starting with //
        lines = [
            line for line in raw.splitlines()
            if not line.strip().startswith("//")
        ]
        data = json.loads("\n".join(lines))

    servers = data.get("servers", {})
    if server_name not in servers:
        available = ", ".join(servers.keys())
        raise KeyError(
            f"Server '{server_name}' not found in {config_path}. "
            f"Available: {available}"
        )

    entry = servers[server_name]
    return MCPServerConfig(
        name=server_name,
        url=entry["url"],
        server_type=entry.get("type", "http"),
        headers=entry.get("headers", {}),
    )

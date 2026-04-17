"""HTTP client for the Fabric Data Agent MCP server.

Sends natural-language questions to the MCP endpoint and returns the
agent's textual response.
"""

import json
import logging
from typing import Optional

import requests

from .config import MCPServerConfig

logger = logging.getLogger(__name__)

# Fabric / Power BI API scope used by the Data Agent
_FABRIC_SCOPE = "https://analysis.windows.net/powerbi/api/.default"


class MCPClient:
    """Client for calling a Fabric Data Agent via the MCP protocol."""

    def __init__(self, config: MCPServerConfig, token: Optional[str] = None):
        """Initialise the client.

        Args:
            config: MCP server configuration (URL, headers, etc.).
            token: Optional pre-supplied bearer token.  If *None*,
                the client will attempt to acquire one via
                ``azure.identity.DefaultAzureCredential``.
        """
        self.config = config
        self._token = token

    # ------------------------------------------------------------------
    # Token helpers
    # ------------------------------------------------------------------

    def _get_token(self) -> str:
        """Return a bearer token, acquiring one if necessary."""
        if self._token:
            return self._token
        try:
            from azure.identity import DefaultAzureCredential  # type: ignore

            credential = DefaultAzureCredential()
            token_result = credential.get_token(_FABRIC_SCOPE)
            self._token = token_result.token
            return self._token
        except ImportError:
            raise RuntimeError(
                "azure-identity is not installed.  Install it with:\n"
                "  pip install azure-identity\n"
                "Or supply a bearer token explicitly."
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to acquire Azure token: {exc}") from exc

    # ------------------------------------------------------------------
    # MCP call
    # ------------------------------------------------------------------

    def ask(self, question: str) -> str:
        """Send a natural-language question to the Data Agent.

        Args:
            question: The question string.

        Returns:
            The agent's textual response.

        Raises:
            requests.HTTPError: On non-2xx responses.
            RuntimeError: If the response cannot be parsed.
        """
        token = self._get_token()

        headers = {
            "Authorization": f"Bearer {token}",
            **self.config.headers,
        }
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        # MCP JSON-RPC style payload
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "DataAgent_TPM_Diagnostics_Agent",
                "arguments": {"userQuestion": question},
            },
        }

        logger.info("MCP request → %s", question[:120])
        resp = requests.post(
            self.config.url,
            json=payload,
            headers=headers,
            timeout=120,
        )
        resp.raise_for_status()

        return self._extract_text(resp.json())

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(body: dict) -> str:
        """Pull the human-readable answer from the MCP JSON-RPC response."""
        # Typical shape: {"result": {"content": [{"type":"text","text":"..."}]}}
        result = body.get("result", body)

        # If there's a content list, concatenate text entries
        content = result.get("content")
        if isinstance(content, list):
            texts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            if texts:
                return "\n".join(texts)

        # Fallback: look for a top-level text field
        if isinstance(result, dict) and "text" in result:
            return result["text"]

        # Last resort: return the raw JSON for debugging
        return json.dumps(body, indent=2)

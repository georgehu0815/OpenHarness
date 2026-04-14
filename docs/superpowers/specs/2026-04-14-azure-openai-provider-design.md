# Azure OpenAI Provider Design

**Date:** 2026-04-14  
**Status:** Approved

## Goal

Extend the OpenHarness CLI to support Azure OpenAI as a first-class provider with Azure AD identity authentication (`DefaultAzureCredential`), configured via the project's `.env` file, and active by default when `OPENHARNESS_ACTIVE_PROFILE=azure-openai` is set.

## Background

`azure_provider.py` exists but imports from `nanobot.providers.base` — a module that is not installed and not in `pyproject.toml`. It is dead code and will be replaced entirely.

The OpenHarness engine routes all LLM calls through the `SupportsStreamingMessages` protocol (defined in `api/client.py`). Every provider is a concrete class implementing `stream_message(request) -> AsyncIterator[ApiStreamEvent]`. The new `AzureOpenAIClient` must conform to this protocol.

## Source of Truth — Reference Client

```python
import os
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

endpoint   = os.getenv("ENDPOINT_URL", "https://datacopilothub8882317788.openai.azure.com/")
deployment = os.getenv("DEPLOYMENT_NAME", "gpt-5.4-mini")

token_provider = get_bearer_token_provider(
    DefaultAzureCredential(),
    "https://cognitiveservices.azure.com/.default"
)

client = AzureOpenAI(
    azure_endpoint=endpoint,
    azure_ad_token_provider=token_provider,
    api_version="2025-01-01-preview",
)
```

The implementation uses `AsyncAzureOpenAI` (same package, async variant) to match the non-blocking requirements of the engine.

## Architecture

### Components Changed / Added

| File | Change |
|------|--------|
| `src/openharness/api/azure_provider.py` | **Replace** — new `AzureOpenAIClient` class |
| `src/openharness/api/__init__.py` | Export `AzureOpenAIClient` |
| `src/openharness/api/registry.py` | Add `azure_openai` `ProviderSpec` |
| `src/openharness/config/settings.py` | Add `azure-openai` profile; add `OPENHARNESS_ACTIVE_PROFILE` env override |
| `src/openharness/ui/runtime.py` | Add routing branch for `provider == "azure_openai"` |
| `pyproject.toml` | Add `azure-identity>=1.19.0`, `python-dotenv>=1.0.0` |

### Data Flow

```
CLI startup
  └─ load_settings()
       ├─ load_dotenv()          ← loads .env from CWD
       ├─ reads OPENHARNESS_ACTIVE_PROFILE=azure-openai
       └─ returns Settings(active_profile="azure-openai", provider="azure_openai")

_resolve_api_client_from_settings(settings)
  └─ provider == "azure_openai"
       └─ AzureOpenAIClient()
            ├─ reads ENDPOINT_URL      (fallback: hardcoded endpoint)
            ├─ reads DEPLOYMENT_NAME   (fallback: "gpt-5.4-mini")
            ├─ DefaultAzureCredential()
            └─ AsyncAzureOpenAI(azure_endpoint, azure_ad_token_provider, api_version)
```

## `AzureOpenAIClient` Design

**Location:** `src/openharness/api/azure_provider.py`

```python
class AzureOpenAIClient:
    """Azure OpenAI client implementing SupportsStreamingMessages.
    
    Auth: DefaultAzureCredential (Entra ID / Managed Identity).
    Config: ENDPOINT_URL, DEPLOYMENT_NAME env vars.
    """

    def __init__(self, *, timeout: float | None = None) -> None:
        # reads env at construction time (after dotenv load)

    async def stream_message(
        self, request: ApiMessageRequest
    ) -> AsyncIterator[ApiStreamEvent]:
        # same chunked-streaming + tool-call accumulation as OpenAICompatibleClient
        # uses AsyncAzureOpenAI.chat.completions.create(stream=True)
```

- Lazy `AsyncAzureOpenAI` client construction on first call (avoids event-loop binding issues at import time).
- Retry logic: same 3-attempt exponential backoff as `OpenAICompatibleClient`.
- Tool calls: reuses `_convert_tools_to_openai()` and `_convert_messages_to_openai()` from `openai_client.py`.
- Model routing: uses `DEPLOYMENT_NAME` env var; the `request.model` field overrides it if explicitly set by the engine.

## `.env` Loading

`python-dotenv`'s `load_dotenv()` is called at the start of `load_settings()` with `override=False` (env already set by the shell takes precedence). It searches for `.env` in the current working directory.

The user's `.env` (or a local `.env.local`) should contain:

```dotenv
ENDPOINT_URL=https://datacopilothub8882317788.openai.azure.com/
DEPLOYMENT_NAME=gpt-5.4-mini
OPENHARNESS_ACTIVE_PROFILE=azure-openai
```

## Registry Entry

```python
ProviderSpec(
    name="azure_openai",
    keywords=("azure",),
    env_key="ENDPOINT_URL",
    display_name="Azure OpenAI",
    backend_type="azure_openai",
    default_base_url="",
    detect_by_base_keyword="openai.azure.com",
    is_gateway=False,
    is_local=False,
    is_oauth=False,
)
```

## Settings Profile

```python
"azure-openai": ProviderProfile(
    label="Azure OpenAI",
    provider="azure_openai",
    api_format="openai",
    auth_source="azure_identity",       # no stored credential — identity-based
    default_model="gpt-5.4-mini",
)
```

`auth_source="azure_identity"` is a new sentinel that `resolve_auth()` and `auth_status()` handle by returning a fixed "identity" status (no credential lookup needed).

## `_resolve_api_client_from_settings` Routing

New branch added before the `api_format == "openai"` fallback:

```python
if settings.provider == "azure_openai":
    from openharness.api.azure_provider import AzureOpenAIClient
    return AzureOpenAIClient(timeout=settings.timeout)
```

## `_apply_env_overrides` Addition

```python
active_profile = os.environ.get("OPENHARNESS_ACTIVE_PROFILE")
if active_profile:
    updates["active_profile"] = active_profile
```

## `resolve_auth()` Guard

`Settings.resolve_auth()` must short-circuit for `auth_source == "azure_identity"` before reaching the stored-credential lookup (which would raise `ValueError`):

```python
if auth_source == "azure_identity":
    return ResolvedAuth(
        provider="azure_openai",
        auth_kind="azure_identity",
        value="identity",
        source="azure_identity",
        state="configured",
    )
```

## `provider.py` / `auth_status` Addition

`_AUTH_KIND` gains `"azure_openai": "azure_identity"`.  
`detect_provider` gains a branch: `if settings.provider == "azure_openai"` → returns `ProviderInfo(name="azure_openai", auth_kind="azure_identity", ...)`.  
`auth_status` returns `"identity (DefaultAzureCredential)"` for the `azure_openai` provider.

## Error Handling

- If `DefaultAzureCredential` fails (not logged in): the `AsyncAzureOpenAI` call will raise a `ClientAuthenticationError`; the retry logic catches it and surfaces it as `AuthenticationFailure` with a message pointing to `az login`.
- If `ENDPOINT_URL` is unset and the fallback isn't reachable: surfaces as `RequestFailure`.

## Dependencies

```toml
"azure-identity>=1.19.0",
"python-dotenv>=1.0.0",
```

## Testing

- Unit: mock `AsyncAzureOpenAI` and `DefaultAzureCredential`; verify `stream_message` yields correct `ApiTextDeltaEvent` / `ApiMessageCompleteEvent` / tool-call events.
- Integration smoke test: `oh -p "say hello" --active-profile azure-openai` with `.env` loaded.

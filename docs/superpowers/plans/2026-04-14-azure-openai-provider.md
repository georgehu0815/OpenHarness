# Azure OpenAI Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Azure OpenAI as a first-class provider with Entra ID / Managed Identity auth, wired end-to-end so `oh` uses it by default when `.env` is present.

**Architecture:** Replace the dead `azure_provider.py` (which imports a non-existent `nanobot` module) with a new `AzureOpenAIClient` implementing the `SupportsStreamingMessages` protocol. Wire it into the existing client-factory in `ui/runtime.py` via a new `azure_openai` provider type, registered in `api/registry.py` and declared as a `ProviderProfile` in `config/settings.py`. Load `.env` automatically via `python-dotenv` so env vars (`ENDPOINT_URL`, `DEPLOYMENT_NAME`, `OPENHARNESS_ACTIVE_PROFILE`) activate the provider at startup.

**Tech Stack:** `openai>=1.0.0` (`AsyncAzureOpenAI`), `azure-identity>=1.19.0` (`DefaultAzureCredential`, `get_bearer_token_provider`), `python-dotenv>=1.0.0`, `pytest-asyncio`, `unittest.mock`

**Spec:** `docs/superpowers/specs/2026-04-14-azure-openai-provider-design.md`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| **Replace** | `src/openharness/api/azure_provider.py` | `AzureOpenAIClient` — streaming client using `AsyncAzureOpenAI` + `DefaultAzureCredential` |
| **Create** | `tests/test_api/test_azure_provider.py` | Unit tests for `AzureOpenAIClient` |
| **Modify** | `pyproject.toml` | Add `azure-identity>=1.19.0`, `python-dotenv>=1.0.0` |
| **Modify** | `src/openharness/api/__init__.py` | Export `AzureOpenAIClient` |
| **Modify** | `src/openharness/api/registry.py` | Add `azure_openai` `ProviderSpec` |
| **Modify** | `src/openharness/config/settings.py` | Add `azure-openai` profile; `OPENHARNESS_ACTIVE_PROFILE` env override; `resolve_auth()` guard; `auth_source_provider_name` entry; `load_dotenv()` call |
| **Modify** | `src/openharness/api/provider.py` | Add `azure_openai` to `_AUTH_KIND`; `detect_provider` branch; `auth_status` case |
| **Modify** | `src/openharness/ui/runtime.py` | Add `azure_openai` routing branch in `_resolve_api_client_from_settings` |
| **Modify** | `.env` | Add `ENDPOINT_URL`, `DEPLOYMENT_NAME`, `OPENHARNESS_ACTIVE_PROFILE` |

---

## Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add `azure-identity` and `python-dotenv` to `pyproject.toml`**

Open `pyproject.toml`. In the `dependencies` list, add these two lines after `"openai>=1.0.0",`:

```toml
    "azure-identity>=1.19.0",
    "python-dotenv>=1.0.0",
```

The `dependencies` block should look like:
```toml
dependencies = [
    "anthropic>=0.40.0",
    "openai>=1.0.0",
    "azure-identity>=1.19.0",
    "python-dotenv>=1.0.0",
    "rich>=13.0.0",
    ...
]
```

- [ ] **Step 2: Install the new dependencies**

```bash
pip install azure-identity>=1.19.0 python-dotenv>=1.0.0
```

Expected: packages install without error.

- [ ] **Step 3: Verify imports work**

```bash
python3 -c "from azure.identity import DefaultAzureCredential, get_bearer_token_provider; from dotenv import load_dotenv; print('OK')"
```

Expected output: `OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: add azure-identity and python-dotenv dependencies"
```

---

## Task 2: Write `AzureOpenAIClient`

**Files:**
- Replace: `src/openharness/api/azure_provider.py`
- Create: `tests/test_api/test_azure_provider.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api/test_azure_provider.py` with this content:

```python
"""Tests for the Azure OpenAI client."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from openharness.api.client import ApiMessageRequest
from openharness.engine.messages import ConversationMessage, TextBlock, ToolUseBlock


def _make_text_chunk(text: str, finish: str | None = None):
    """Build a fake streaming chunk yielding text content."""
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta.content = text
    chunk.choices[0].delta.tool_calls = None
    chunk.choices[0].finish_reason = finish
    chunk.usage = None
    return chunk


def _make_usage_chunk(prompt: int, completion: int):
    """Build a usage-only chunk (no choices)."""
    chunk = MagicMock()
    chunk.choices = []
    chunk.usage = MagicMock(prompt_tokens=prompt, completion_tokens=completion)
    return chunk


def _make_azure_client(chunks: list) -> MagicMock:
    """Return a mock AsyncAzureOpenAI that streams the given chunks."""
    mock_client = MagicMock()

    async def fake_stream(*_args, **_kwargs):
        for c in chunks:
            yield c

    mock_client.chat.completions.create = fake_stream
    return mock_client


@pytest.fixture
def patched_identity():
    """Patch azure.identity so no real credential is created."""
    with patch("openharness.api.azure_provider.DefaultAzureCredential") as mock_cred, \
         patch("openharness.api.azure_provider.get_bearer_token_provider") as mock_tp:
        mock_tp.return_value = MagicMock()
        yield mock_cred, mock_tp


class TestAzureOpenAIClientInit:
    def test_reads_endpoint_from_env(self, monkeypatch, patched_identity):
        monkeypatch.setenv("ENDPOINT_URL", "https://myendpoint.openai.azure.com/")
        from openharness.api.azure_provider import AzureOpenAIClient
        client = AzureOpenAIClient()
        assert client._endpoint == "https://myendpoint.openai.azure.com/"

    def test_reads_deployment_from_env(self, monkeypatch, patched_identity):
        monkeypatch.setenv("DEPLOYMENT_NAME", "my-deployment")
        from openharness.api.azure_provider import AzureOpenAIClient
        client = AzureOpenAIClient()
        assert client._deployment == "my-deployment"

    def test_default_endpoint_fallback(self, monkeypatch, patched_identity):
        monkeypatch.delenv("ENDPOINT_URL", raising=False)
        from openharness.api.azure_provider import AzureOpenAIClient, _ENDPOINT_DEFAULT
        client = AzureOpenAIClient()
        assert client._endpoint == _ENDPOINT_DEFAULT

    def test_default_deployment_fallback(self, monkeypatch, patched_identity):
        monkeypatch.delenv("DEPLOYMENT_NAME", raising=False)
        from openharness.api.azure_provider import AzureOpenAIClient, _DEPLOYMENT_DEFAULT
        client = AzureOpenAIClient()
        assert client._deployment == _DEPLOYMENT_DEFAULT


class TestAzureOpenAIClientStreaming:
    def _make_client(self, monkeypatch, patched_identity):
        monkeypatch.setenv("ENDPOINT_URL", "https://test.openai.azure.com/")
        monkeypatch.setenv("DEPLOYMENT_NAME", "gpt-test")
        from openharness.api.azure_provider import AzureOpenAIClient
        client = AzureOpenAIClient()
        return client

    def _make_request(self, text: str = "hello") -> ApiMessageRequest:
        return ApiMessageRequest(
            model="gpt-test",
            messages=[ConversationMessage(role="user", content=[TextBlock(text=text)])],
            system_prompt=None,
            max_tokens=100,
        )

    @pytest.mark.asyncio
    async def test_yields_text_delta_events(self, monkeypatch, patched_identity):
        from openharness.api.client import ApiTextDeltaEvent
        client = self._make_client(monkeypatch, patched_identity)
        client._client = _make_azure_client([
            _make_text_chunk("hello"),
            _make_text_chunk(" world", finish="stop"),
            _make_usage_chunk(10, 5),
        ])

        events = []
        async for event in client.stream_message(self._make_request()):
            events.append(event)

        from openharness.api.client import ApiMessageCompleteEvent
        text_events = [e for e in events if isinstance(e, ApiTextDeltaEvent)]
        complete_events = [e for e in events if isinstance(e, ApiMessageCompleteEvent)]

        assert [e.text for e in text_events] == ["hello", " world"]
        assert len(complete_events) == 1
        assert complete_events[0].stop_reason == "stop"
        assert complete_events[0].usage.input_tokens == 10
        assert complete_events[0].usage.output_tokens == 5

    @pytest.mark.asyncio
    async def test_complete_event_has_text_content(self, monkeypatch, patched_identity):
        from openharness.api.client import ApiMessageCompleteEvent
        client = self._make_client(monkeypatch, patched_identity)
        client._client = _make_azure_client([
            _make_text_chunk("hi", finish="stop"),
        ])

        events = []
        async for event in client.stream_message(self._make_request()):
            events.append(event)

        complete = next(e for e in events if isinstance(e, ApiMessageCompleteEvent))
        assert complete.message.role == "assistant"
        assert any(
            isinstance(b, TextBlock) and b.text == "hi"
            for b in complete.message.content
        )

    @pytest.mark.asyncio
    async def test_strips_azure_prefix_from_model(self, monkeypatch, patched_identity):
        """model='azure/gpt-4o' should be sent as 'gpt-4o' to the API."""
        client = self._make_client(monkeypatch, patched_identity)

        called_model = None

        async def fake_stream(model, **_kwargs):
            nonlocal called_model
            called_model = model
            yield _make_text_chunk("ok", finish="stop")

        # Patch at the correct level
        mock_client = MagicMock()
        mock_client.chat.completions.create = fake_stream
        client._client = mock_client

        request = ApiMessageRequest(
            model="azure/gpt-4o",
            messages=[ConversationMessage(role="user", content=[TextBlock(text="hi")])],
            system_prompt=None,
            max_tokens=100,
        )
        async for _ in client.stream_message(request):
            pass

        assert called_model == "gpt-4o"

    @pytest.mark.asyncio
    async def test_translates_401_to_authentication_failure(self, monkeypatch, patched_identity):
        from openharness.api.errors import AuthenticationFailure
        client = self._make_client(monkeypatch, patched_identity)

        error = Exception("unauthorized")
        error.status_code = 401  # type: ignore[attr-defined]

        async def fail_stream(**_kwargs):
            raise error
            yield  # make it an async generator

        mock_client = MagicMock()
        mock_client.chat.completions.create = fail_stream
        client._client = mock_client

        with pytest.raises(AuthenticationFailure):
            async for _ in client.stream_message(self._make_request()):
                pass
```

- [ ] **Step 2: Run tests — verify they all FAIL**

```bash
cd /Volumes/ExternalSSD/train/OpenHarness && python3 -m pytest tests/test_api/test_azure_provider.py -v 2>&1 | tail -20
```

Expected: `ImportError` or `ModuleNotFoundError` — `AzureOpenAIClient` doesn't exist yet.

- [ ] **Step 3: Replace `azure_provider.py` with the new implementation**

Replace the entire contents of `src/openharness/api/azure_provider.py` with:

```python
"""Azure OpenAI client with Entra ID / Managed Identity authentication."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, AsyncIterator

from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from openharness.api.client import (
    ApiMessageCompleteEvent,
    ApiMessageRequest,
    ApiRetryEvent,
    ApiStreamEvent,
    ApiTextDeltaEvent,
)
from openharness.api.errors import (
    AuthenticationFailure,
    OpenHarnessApiError,
    RateLimitFailure,
    RequestFailure,
)
from openharness.api.usage import UsageSnapshot
from openharness.engine.messages import ContentBlock, ConversationMessage, TextBlock, ToolUseBlock

log = logging.getLogger(__name__)

_ENDPOINT_DEFAULT = "https://datacopilothub8882317788.openai.azure.com/"
_DEPLOYMENT_DEFAULT = "gpt-5.4-mini"
_API_VERSION = "2025-01-01-preview"
_COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"

MAX_RETRIES = 3
BASE_DELAY = 1.0
MAX_DELAY = 30.0


class AzureOpenAIClient:
    """Azure OpenAI client implementing SupportsStreamingMessages.

    Authentication: DefaultAzureCredential (Entra ID / Managed Identity).
    No API key required — uses the Azure identity of the logged-in user or
    the managed identity of the host (``az login`` for local dev).

    Configuration via environment variables:
        ENDPOINT_URL    — Azure OpenAI endpoint URL
                          (default: https://datacopilothub8882317788.openai.azure.com/)
        DEPLOYMENT_NAME — deployment / model name (default: gpt-5.4-mini)
    """

    def __init__(self, *, timeout: float | None = None) -> None:
        self._endpoint = os.getenv("ENDPOINT_URL", _ENDPOINT_DEFAULT)
        self._deployment = os.getenv("DEPLOYMENT_NAME", _DEPLOYMENT_DEFAULT)
        self._timeout = timeout
        self._token_provider = get_bearer_token_provider(
            DefaultAzureCredential(),
            _COGNITIVE_SERVICES_SCOPE,
        )
        # Lazy — created on first call to avoid event-loop binding at import time
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import AsyncAzureOpenAI

            kwargs: dict[str, Any] = {
                "azure_endpoint": self._endpoint,
                "azure_ad_token_provider": self._token_provider,
                "api_version": _API_VERSION,
            }
            if self._timeout is not None:
                kwargs["timeout"] = self._timeout
            self._client = AsyncAzureOpenAI(**kwargs)
        return self._client

    async def stream_message(
        self, request: ApiMessageRequest
    ) -> AsyncIterator[ApiStreamEvent]:
        """Yield text deltas and the final message, matching the Anthropic client interface."""
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                async for event in self._stream_once(request):
                    yield event
                return
            except OpenHarnessApiError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt >= MAX_RETRIES or not self._is_retryable(exc):
                    raise self._translate_error(exc) from exc

                delay = min(BASE_DELAY * (2**attempt), MAX_DELAY)
                log.warning(
                    "Azure OpenAI request failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    MAX_RETRIES + 1,
                    delay,
                    exc,
                )
                yield ApiRetryEvent(
                    message=str(exc),
                    attempt=attempt + 1,
                    max_attempts=MAX_RETRIES + 1,
                    delay_seconds=delay,
                )
                await asyncio.sleep(delay)

        if last_error is not None:
            raise self._translate_error(last_error) from last_error

    async def _stream_once(
        self, request: ApiMessageRequest
    ) -> AsyncIterator[ApiStreamEvent]:
        """Single attempt: stream one Azure OpenAI chat completion."""
        from openharness.api.openai_client import (
            _convert_messages_to_openai,
            _convert_tools_to_openai,
            _token_limit_param_for_model,
        )

        deployment = request.model or self._deployment
        if deployment.startswith("azure/"):
            deployment = deployment[6:]

        openai_messages = _convert_messages_to_openai(
            request.messages, request.system_prompt
        )
        openai_tools = _convert_tools_to_openai(request.tools) if request.tools else None

        params: dict[str, Any] = {
            "model": deployment,
            "messages": openai_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        params.update(_token_limit_param_for_model(deployment, request.max_tokens))
        if openai_tools:
            params["tools"] = openai_tools
            params.pop("stream_options", None)

        collected_content = ""
        collected_tool_calls: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        usage_data: dict[str, int] = {}

        async for chunk in self._get_client().chat.completions.create(**params):
            if not chunk.choices:
                if chunk.usage:
                    usage_data = {
                        "input_tokens": chunk.usage.prompt_tokens or 0,
                        "output_tokens": chunk.usage.completion_tokens or 0,
                    }
                continue

            delta = chunk.choices[0].delta
            chunk_finish = chunk.choices[0].finish_reason
            if chunk_finish:
                finish_reason = chunk_finish

            if delta.content:
                collected_content += delta.content
                yield ApiTextDeltaEvent(text=delta.content)

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in collected_tool_calls:
                        collected_tool_calls[idx] = {
                            "id": tc_delta.id or "",
                            "name": "",
                            "arguments": "",
                        }
                    entry = collected_tool_calls[idx]
                    if tc_delta.id:
                        entry["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            entry["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            entry["arguments"] += tc_delta.function.arguments

            if chunk.usage:
                usage_data = {
                    "input_tokens": chunk.usage.prompt_tokens or 0,
                    "output_tokens": chunk.usage.completion_tokens or 0,
                }

        content: list[ContentBlock] = []
        if collected_content:
            content.append(TextBlock(text=collected_content))

        for _idx in sorted(collected_tool_calls.keys()):
            tc = collected_tool_calls[_idx]
            if not tc["name"]:
                continue
            try:
                args = json.loads(tc["arguments"])
            except (json.JSONDecodeError, TypeError):
                args = {}
            content.append(ToolUseBlock(id=tc["id"], name=tc["name"], input=args))

        final_message = ConversationMessage(role="assistant", content=content)

        yield ApiMessageCompleteEvent(
            message=final_message,
            usage=UsageSnapshot(
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
            ),
            stop_reason=finish_reason,
        )

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        status = getattr(exc, "status_code", None)
        if status and status in {429, 500, 502, 503}:
            return True
        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            return True
        return False

    @staticmethod
    def _translate_error(exc: Exception) -> OpenHarnessApiError:
        status = getattr(exc, "status_code", None)
        msg = str(exc)
        if status in {401, 403}:
            return AuthenticationFailure(msg)
        if status == 429:
            return RateLimitFailure(msg)
        return RequestFailure(msg)
```

- [ ] **Step 4: Run tests — verify they all PASS**

```bash
cd /Volumes/ExternalSSD/train/OpenHarness && python3 -m pytest tests/test_api/test_azure_provider.py -v
```

Expected output: all tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/openharness/api/azure_provider.py tests/test_api/test_azure_provider.py
git commit -m "feat(api): add AzureOpenAIClient with DefaultAzureCredential identity auth"
```

---

## Task 3: Register `azure_openai` provider

**Files:**
- Modify: `src/openharness/api/registry.py:296-354`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api/test_azure_provider.py`:

```python
class TestAzureProviderRegistry:
    def test_azure_spec_in_providers(self):
        from openharness.api.registry import PROVIDERS
        names = [s.name for s in PROVIDERS]
        assert "azure_openai" in names

    def test_azure_spec_detects_by_base_url(self):
        from openharness.api.registry import detect_provider_from_registry
        spec = detect_provider_from_registry(
            model="",
            base_url="https://myhub.openai.azure.com/",
        )
        assert spec is not None
        assert spec.name == "azure_openai"

    def test_azure_spec_detects_by_keyword(self):
        from openharness.api.registry import detect_provider_from_registry
        spec = detect_provider_from_registry(model="azure/gpt-4o")
        assert spec is not None
        assert spec.name == "azure_openai"
```

- [ ] **Step 2: Run — verify FAIL**

```bash
python3 -m pytest tests/test_api/test_azure_provider.py::TestAzureProviderRegistry -v
```

Expected: `AssertionError` — `azure_openai` not in `PROVIDERS`.

- [ ] **Step 3: Add `azure_openai` ProviderSpec to `registry.py`**

In `src/openharness/api/registry.py`, add this entry to the `PROVIDERS` tuple, just before the `# === Local deployments` section (after Vertex AI, around line 325):

```python
    # Azure OpenAI (Entra ID / Managed Identity — no API key)
    ProviderSpec(
        name="azure_openai",
        keywords=("azure",),
        env_key="ENDPOINT_URL",
        display_name="Azure OpenAI",
        backend_type="azure_openai",
        default_base_url="",
        detect_by_key_prefix="",
        detect_by_base_keyword="openai.azure.com",
        is_gateway=False,
        is_local=False,
        is_oauth=False,
    ),
```

- [ ] **Step 4: Run — verify PASS**

```bash
python3 -m pytest tests/test_api/test_azure_provider.py::TestAzureProviderRegistry -v
```

Expected: all three tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/openharness/api/registry.py tests/test_api/test_azure_provider.py
git commit -m "feat(registry): register azure_openai provider spec"
```

---

## Task 4: Add `azure-openai` settings profile and `resolve_auth` guard

**Files:**
- Modify: `src/openharness/config/settings.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config/test_azure_settings.py`:

```python
"""Tests for Azure OpenAI settings integration."""

from __future__ import annotations

import pytest
from openharness.config.settings import (
    Settings,
    default_provider_profiles,
    auth_source_provider_name,
)


class TestAzureProfile:
    def test_azure_openai_profile_exists(self):
        profiles = default_provider_profiles()
        assert "azure-openai" in profiles

    def test_azure_openai_profile_fields(self):
        profile = default_provider_profiles()["azure-openai"]
        assert profile.provider == "azure_openai"
        assert profile.api_format == "openai"
        assert profile.auth_source == "azure_identity"
        assert profile.default_model == "gpt-5.4-mini"

    def test_auth_source_provider_name_azure(self):
        result = auth_source_provider_name("azure_identity")
        assert result == "azure_openai"


class TestResolveAuthAzureIdentity:
    def test_resolve_auth_returns_identity_sentinel(self):
        settings = Settings(
            active_profile="azure-openai",
            profiles=default_provider_profiles(),
        ).materialize_active_profile()
        auth = settings.resolve_auth()
        assert auth.auth_kind == "azure_identity"
        assert auth.provider == "azure_openai"
        assert auth.value == "identity"

    def test_resolve_auth_does_not_raise_for_azure(self):
        """Must not raise ValueError trying to look up a stored credential."""
        settings = Settings(
            active_profile="azure-openai",
            profiles=default_provider_profiles(),
        ).materialize_active_profile()
        # Should not raise
        auth = settings.resolve_auth()
        assert auth is not None
```

- [ ] **Step 2: Run — verify FAIL**

```bash
python3 -m pytest tests/test_config/test_azure_settings.py -v
```

Expected: `AssertionError` — `azure-openai` not in profiles.

- [ ] **Step 3: Add `azure-openai` profile to `default_provider_profiles()` in `settings.py`**

In `src/openharness/config/settings.py`, find `default_provider_profiles()` and add this entry to the returned dict (after the `"gemini"` entry):

```python
        "azure-openai": ProviderProfile(
            label="Azure OpenAI",
            provider="azure_openai",
            api_format="openai",
            auth_source="azure_identity",
            default_model="gpt-5.4-mini",
        ),
```

- [ ] **Step 4: Add `azure_identity` to `auth_source_provider_name` mapping in `settings.py`**

In `src/openharness/config/settings.py`, find the `auth_source_provider_name` function and add this entry to its `mapping` dict:

```python
        "azure_identity": "azure_openai",
```

- [ ] **Step 5: Add `resolve_auth()` short-circuit for `azure_identity` in `settings.py`**

In `src/openharness/config/settings.py`, find `Settings.resolve_auth()`. At the top of the method, after the line that resolves `auth_source`, add this guard block (before the `if auth_source in {"codex_subscription", "claude_subscription"}:` check):

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

- [ ] **Step 6: Run — verify PASS**

```bash
python3 -m pytest tests/test_config/test_azure_settings.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 7: Commit**

```bash
git add src/openharness/config/settings.py tests/test_config/test_azure_settings.py
git commit -m "feat(settings): add azure-openai provider profile with identity auth"
```

---

## Task 5: Load `.env` and support `OPENHARNESS_ACTIVE_PROFILE`

**Files:**
- Modify: `src/openharness/config/settings.py` (`load_settings`, `_apply_env_overrides`)
- Modify: `.env`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config/test_azure_settings.py`:

```python
class TestDotenvLoading:
    def test_active_profile_env_override(self, monkeypatch):
        """OPENHARNESS_ACTIVE_PROFILE env var should override the active profile."""
        monkeypatch.setenv("OPENHARNESS_ACTIVE_PROFILE", "azure-openai")
        # Re-import to pick up the env var via _apply_env_overrides
        from openharness.config.settings import Settings, _apply_env_overrides, default_provider_profiles
        base = Settings(profiles=default_provider_profiles())
        result = _apply_env_overrides(base)
        assert result.active_profile == "azure-openai"
```

- [ ] **Step 2: Run — verify FAIL**

```bash
python3 -m pytest tests/test_config/test_azure_settings.py::TestDotenvLoading -v
```

Expected: `AssertionError` — `active_profile` is not `"azure-openai"`.

- [ ] **Step 3: Add `OPENHARNESS_ACTIVE_PROFILE` to `_apply_env_overrides` in `settings.py`**

In `src/openharness/config/settings.py`, find `_apply_env_overrides`. Add this block anywhere in the `updates` section (e.g. after the `provider` block):

```python
    active_profile = os.environ.get("OPENHARNESS_ACTIVE_PROFILE")
    if active_profile:
        updates["active_profile"] = active_profile
```

- [ ] **Step 4: Add `load_dotenv()` call to `load_settings()` in `settings.py`**

In `src/openharness/config/settings.py`, find `load_settings()`. Add the `load_dotenv` call as the very first line inside the function body:

```python
def load_settings(config_path: Path | None = None) -> Settings:
    """Load settings from config file, merging with defaults."""
    from dotenv import load_dotenv
    load_dotenv(override=False)   # load .env from CWD; shell env takes precedence
    ...
```

(`override=False` ensures that vars already set in the shell are not overwritten by `.env`.)

- [ ] **Step 5: Run — verify PASS**

```bash
python3 -m pytest tests/test_config/test_azure_settings.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 6: Add vars to `.env`**

Open `.env` and append these three lines at the end:

```dotenv
ENDPOINT_URL="https://datacopilothub8882317788.openai.azure.com/"
DEPLOYMENT_NAME="gpt-5.4-mini"
OPENHARNESS_ACTIVE_PROFILE="azure-openai"
```

- [ ] **Step 7: Commit**

```bash
git add src/openharness/config/settings.py tests/test_config/test_azure_settings.py .env
git commit -m "feat(settings): load .env at startup and support OPENHARNESS_ACTIVE_PROFILE"
```

---

## Task 6: Wire `provider.py` detection for `azure_openai`

**Files:**
- Modify: `src/openharness/api/provider.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api/test_azure_provider_detection.py`:

```python
"""Tests for Azure OpenAI provider detection."""

from __future__ import annotations

import pytest
from unittest.mock import patch
from openharness.config.settings import Settings, default_provider_profiles


class TestDetectAzureProvider:
    def _azure_settings(self) -> Settings:
        return Settings(
            active_profile="azure-openai",
            profiles=default_provider_profiles(),
        ).materialize_active_profile()

    def test_detect_provider_returns_azure_name(self):
        from openharness.api.provider import detect_provider
        info = detect_provider(self._azure_settings())
        assert info.name == "azure_openai"

    def test_detect_provider_auth_kind_is_identity(self):
        from openharness.api.provider import detect_provider
        info = detect_provider(self._azure_settings())
        assert info.auth_kind == "azure_identity"

    def test_auth_status_returns_identity_string(self):
        from openharness.api.provider import auth_status
        status = auth_status(self._azure_settings())
        assert "identity" in status.lower()
```

- [ ] **Step 2: Run — verify FAIL**

```bash
python3 -m pytest tests/test_api/test_azure_provider_detection.py -v
```

Expected: `AssertionError` — `detect_provider` doesn't handle `azure_openai`.

- [ ] **Step 3: Update `provider.py`**

In `src/openharness/api/provider.py`:

**a)** Add `"azure_openai"` to `_AUTH_KIND`:
```python
_AUTH_KIND: dict[str, str] = {
    "anthropic": "api_key",
    "openai_compat": "api_key",
    "copilot": "oauth_device",
    "openai_codex": "external_oauth",
    "anthropic_claude": "external_oauth",
    "azure_openai": "azure_identity",    # ← add this
}
```

**b)** Add a `_VOICE_REASON` entry:
```python
_VOICE_REASON: dict[str, str] = {
    ...
    "azure_openai": "voice mode is not supported for Azure OpenAI",  # ← add this
}
```

**c)** Add a branch in `detect_provider()`, after the `anthropic_claude` check and before the `api_format == "copilot"` check:
```python
    if settings.provider == "azure_openai":
        return ProviderInfo(
            name="azure_openai",
            auth_kind="azure_identity",
            voice_supported=False,
            voice_reason=_VOICE_REASON["azure_openai"],
        )
```

**d)** In `auth_status()`, add a check before the `try` block:
```python
    if settings.provider == "azure_openai":
        return "identity (DefaultAzureCredential)"
```

- [ ] **Step 4: Run — verify PASS**

```bash
python3 -m pytest tests/test_api/test_azure_provider_detection.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add src/openharness/api/provider.py tests/test_api/test_azure_provider_detection.py
git commit -m "feat(provider): add azure_openai detection and auth_status"
```

---

## Task 7: Wire client factory and export

**Files:**
- Modify: `src/openharness/ui/runtime.py:117-165`
- Modify: `src/openharness/api/__init__.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_api/test_azure_provider_detection.py`:

```python
class TestClientFactory:
    def test_azure_settings_produce_azure_client(self):
        from openharness.config.settings import Settings, default_provider_profiles
        from openharness.ui.runtime import _resolve_api_client_from_settings
        from openharness.api.azure_provider import AzureOpenAIClient

        settings = Settings(
            active_profile="azure-openai",
            profiles=default_provider_profiles(),
        ).materialize_active_profile()

        from unittest.mock import patch
        with patch("openharness.api.azure_provider.DefaultAzureCredential"), \
             patch("openharness.api.azure_provider.get_bearer_token_provider"):
            client = _resolve_api_client_from_settings(settings)

        assert isinstance(client, AzureOpenAIClient)
```

- [ ] **Step 2: Run — verify FAIL**

```bash
python3 -m pytest tests/test_api/test_azure_provider_detection.py::TestClientFactory -v
```

Expected: `AssertionError` — factory returns `AnthropicApiClient` or raises, not `AzureOpenAIClient`.

- [ ] **Step 3: Add `azure_openai` branch to `_resolve_api_client_from_settings` in `runtime.py`**

In `src/openharness/ui/runtime.py`, find `_resolve_api_client_from_settings`. Add this branch immediately before the `if settings.api_format == "openai":` block (around line 154):

```python
    if settings.provider == "azure_openai":
        from openharness.api.azure_provider import AzureOpenAIClient
        return AzureOpenAIClient(timeout=settings.timeout)
```

- [ ] **Step 4: Export `AzureOpenAIClient` from `api/__init__.py`**

In `src/openharness/api/__init__.py`, add the import and export:

```python
from openharness.api.azure_provider import AzureOpenAIClient
```

And add `"AzureOpenAIClient"` to `__all__`.

- [ ] **Step 5: Run — verify PASS**

```bash
python3 -m pytest tests/test_api/test_azure_provider_detection.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 6: Run the full test suite to check for regressions**

```bash
python3 -m pytest tests/test_api/ tests/test_config/ -v --tb=short 2>&1 | tail -30
```

Expected: no regressions — all pre-existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add src/openharness/ui/runtime.py src/openharness/api/__init__.py tests/test_api/test_azure_provider_detection.py
git commit -m "feat(runtime): wire AzureOpenAIClient into client factory"
```

---

## Task 8: Smoke-test the CLI end-to-end

> Prerequisite: `az login` completed so `DefaultAzureCredential` can resolve.

- [ ] **Step 1: Install the package in development mode (if not already)**

```bash
cd /Volumes/ExternalSSD/train/OpenHarness && pip install -e .
```

Expected: installs without error.

- [ ] **Step 2: Verify `.env` is loaded and the right provider activates**

```bash
cd /Volumes/ExternalSSD/train/OpenHarness && python3 -c "
from openharness.config.settings import load_settings
s = load_settings()
print('active_profile:', s.active_profile)
print('provider:', s.provider)
print('model:', s.model)
"
```

Expected output:
```
active_profile: azure-openai
provider: azure_openai
model: gpt-5.4-mini
```

- [ ] **Step 3: Smoke-test a single non-interactive query**

```bash
cd /Volumes/ExternalSSD/train/OpenHarness && oh -p "say the word hello and nothing else"
```

Expected: the CLI prints `hello` (or similar) via Azure OpenAI — no auth errors, no import errors.

- [ ] **Step 4: Commit if any incidental fixes were needed**

```bash
git add -p   # stage only intentional fixes
git commit -m "fix: address issues found during Azure OpenAI smoke test"
```

---

## Self-Review Checklist

- [x] **`azure_provider.py`** — fully replaces dead nanobot code; implements `SupportsStreamingMessages`
- [x] **`registry.py`** — `azure_openai` ProviderSpec with `detect_by_base_keyword="openai.azure.com"` and keyword `"azure"`
- [x] **`settings.py`** — `azure-openai` profile; `azure_identity` auth source; `resolve_auth` short-circuit; `load_dotenv`; `OPENHARNESS_ACTIVE_PROFILE`
- [x] **`provider.py`** — `_AUTH_KIND`, `detect_provider`, `auth_status` all handle `azure_openai`
- [x] **`runtime.py`** — factory branch before `api_format == "openai"` fallback
- [x] **`api/__init__.py`** — exports `AzureOpenAIClient`
- [x] **`.env`** — `ENDPOINT_URL`, `DEPLOYMENT_NAME`, `OPENHARNESS_ACTIVE_PROFILE` added
- [x] **`pyproject.toml`** — `azure-identity`, `python-dotenv` added
- [x] **Tests** — TDD for all non-trivial logic; mocks isolate `DefaultAzureCredential` from CI

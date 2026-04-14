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

        async def fake_stream(**kwargs):
            nonlocal called_model
            called_model = kwargs.get("model")
            yield _make_text_chunk("ok", finish="stop")

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

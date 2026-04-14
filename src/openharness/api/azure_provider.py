"""Azure OpenAI client with Entra ID / Managed Identity authentication."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, AsyncIterator

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

# _ENDPOINT_DEFAULT intentionally removed — ENDPOINT_URL must be set explicitly
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
        ENDPOINT_URL    — Azure OpenAI endpoint URL (required)
        DEPLOYMENT_NAME — deployment / model name (default: gpt-5.4-mini)
    """

    def __init__(self, *, timeout: float | None = None) -> None:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        endpoint = os.getenv("ENDPOINT_URL")
        if not endpoint:
            raise ValueError(
                "ENDPOINT_URL environment variable is required for AzureOpenAIClient. "
                "Set it to your Azure OpenAI endpoint, e.g. https://<name>.openai.azure.com/"
            )
        self._endpoint = endpoint
        self._deployment = os.getenv("DEPLOYMENT_NAME", _DEPLOYMENT_DEFAULT)
        self._timeout = timeout
        self._token_provider = get_bearer_token_provider(
            DefaultAzureCredential(),
            _COGNITIVE_SERVICES_SCOPE,
        )
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
        collected_reasoning = ""
        collected_tool_calls: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        usage_data: dict[str, int] = {}

        stream = await self._get_client().chat.completions.create(**params)
        async for chunk in stream:
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

            # Accumulate reasoning_content from thinking models (not shown to user)
            reasoning_piece = getattr(delta, "reasoning_content", None) or ""
            if reasoning_piece:
                collected_reasoning += reasoning_piece

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
        if collected_reasoning:
            final_message._reasoning = collected_reasoning  # type: ignore[attr-defined]

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
        # Cover all 5xx codes (not just 500/502/503) because Azure infrastructure
        # returns a wider variety of transient 5xx responses (e.g. 504, 507, 529).
        status = getattr(exc, "status_code", None)
        if status == 429 or (isinstance(status, int) and 500 <= status <= 599):
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

"""Tests for WebUIChannel — FastAPI SSE gateway channel."""
from __future__ import annotations

import asyncio
import json

import pytest
from httpx import AsyncClient, ASGITransport

from openharness.channels.bus.events import OutboundMessage
from openharness.channels.bus.queue import MessageBus
from openharness.channels.impl.webui import WebUIChannel
from openharness.config.schema import WebUIConfig


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def channel(bus):
    cfg = WebUIConfig(enabled=True, port=8080, allow_from=["*"])
    return WebUIChannel(cfg, bus)


@pytest.fixture
def client(channel):
    return AsyncClient(transport=ASGITransport(app=channel._app), base_url="http://test")


async def test_post_chat_enqueues_inbound_message(client, bus):
    resp = await client.post("/api/chat", json={"session_id": "s1", "message": "hello"})
    assert resp.status_code == 202
    msg = await asyncio.wait_for(bus.inbound.get(), timeout=1.0)
    assert msg.content == "hello"
    assert msg.channel == "webui"
    assert msg.chat_id == "s1"


async def test_session_key_format(client, bus):
    await client.post("/api/chat", json={"session_id": "abc", "message": "ping"})
    msg = await asyncio.wait_for(bus.inbound.get(), timeout=1.0)
    assert msg.session_key == "webui:abc"


async def test_sse_stream_receives_outbound_message(channel, client):
    async def push_after_connect():
        await asyncio.sleep(0.05)
        await channel.send(OutboundMessage(
            channel="webui",
            chat_id="s2",
            content="Hello from agent",
            metadata={},
        ))

    asyncio.create_task(push_after_connect())

    events = []
    async with client.stream("GET", "/api/stream?session_id=s2") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        async for line in resp.aiter_lines():
            if line.startswith("data:"):
                data = json.loads(line[5:].strip())
                events.append(data)
                if data.get("type") in ("final", "progress"):
                    break

    assert any(e.get("message") == "Hello from agent" for e in events)


async def test_stop_cleans_up_queues(channel):
    # Create a queue by registering directly (stop() should drain and clear them)
    q: asyncio.Queue = asyncio.Queue()
    channel._queues["cleanup-test"] = q
    assert "cleanup-test" in channel._queues
    await channel.stop()
    assert "cleanup-test" not in channel._queues

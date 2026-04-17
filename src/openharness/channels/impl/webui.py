"""WebUI channel — exposes the gateway over HTTP/SSE for browser clients."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from openharness.channels.bus.events import OutboundMessage
from openharness.channels.bus.queue import MessageBus
from openharness.channels.impl.base import BaseChannel
from openharness.config.schema import WebUIConfig

logger = logging.getLogger(__name__)

_SENTINEL: Any = object()


class WebUIChannel(BaseChannel):
    """HTTP/SSE channel for the browser-based chat interface."""

    name = "webui"

    def __init__(self, config: WebUIConfig, bus: MessageBus) -> None:
        super().__init__(config, bus)
        self._queues: dict[str, asyncio.Queue] = {}
        self._server = None
        self._app = self._build_app()

    # ------------------------------------------------------------------
    # BaseChannel interface
    # ------------------------------------------------------------------

    async def start(self) -> None:
        import uvicorn

        self._running = True
        port: int = getattr(self.config, "port", 8080)
        config = uvicorn.Config(
            self._app,
            host="0.0.0.0",
            port=port,
            log_level="warning",
            loop="asyncio",
        )
        self._server = uvicorn.Server(config)
        logger.info("WebUI channel starting on port %d", port)
        await self._server.serve()

    async def stop(self) -> None:
        self._running = False
        if self._server is not None:
            self._server.should_exit = True
        for queue in list(self._queues.values()):
            await queue.put(_SENTINEL)
        self._queues.clear()

    async def send(self, msg: OutboundMessage) -> None:
        queue = self._queues.get(msg.chat_id)
        if queue is None:
            return
        is_progress = bool(msg.metadata.get("_progress"))
        event_type = "progress" if is_progress else "final"
        await queue.put({"type": event_type, "message": msg.content})

    # ------------------------------------------------------------------
    # FastAPI app
    # ------------------------------------------------------------------

    def _build_app(self) -> FastAPI:
        app = FastAPI(title="ohmo WebUI API")

        cors_origins: list[str] = list(getattr(self.config, "cors_origins", []))
        if cors_origins:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=cors_origins,
                allow_methods=["GET", "POST", "OPTIONS"],
                allow_headers=["*"],
            )

        @app.post("/api/chat", status_code=202)
        async def post_chat(request: Request) -> dict:
            body = await request.json()
            session_id: str = str(body.get("session_id", ""))
            message: str = str(body.get("message", ""))
            await self._handle_message(
                sender_id=session_id,
                chat_id=session_id,
                content=message,
                session_key=f"webui:{session_id}",
            )
            return {"status": "accepted"}

        @app.get("/api/stream")
        async def get_stream(session_id: str) -> StreamingResponse:
            queue: asyncio.Queue = asyncio.Queue()
            self._queues[session_id] = queue

            async def event_generator():
                try:
                    while True:
                        try:
                            event = await asyncio.wait_for(queue.get(), timeout=30.0)
                        except asyncio.TimeoutError:
                            yield ": keepalive\n\n"
                            continue
                        if event is _SENTINEL:
                            break
                        yield f"data: {json.dumps(event)}\n\n"
                        # Close stream after a final (non-progress) message
                        if isinstance(event, dict) and event.get("type") == "final":
                            break
                except asyncio.CancelledError:
                    pass
                finally:
                    self._queues.pop(session_id, None)

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "Connection": "keep-alive",
                },
            )

        @app.get("/api/sessions")
        async def get_sessions() -> dict:
            return {"sessions": list(self._queues.keys())}

        return app

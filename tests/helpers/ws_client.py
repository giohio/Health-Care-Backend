"""WebSocket test client for notification tests."""

import asyncio
import json
from typing import Optional

import websockets

# Protocol scheme mappings - use constants to avoid hardcoded string literals
_HTTP_SCHEME = "http://"
_HTTPS_SCHEME = "https://"
_WS_SCHEME = "ws://"
_WSS_SCHEME = "wss://"


def _to_ws_base_url(base_url: str) -> str:
    """Convert HTTP/HTTPS URL to secure WebSocket URL (WSS/WS)."""
    if base_url.startswith(_HTTPS_SCHEME):
        return _WSS_SCHEME + base_url[len(_HTTPS_SCHEME) :]
    if base_url.startswith(_HTTP_SCHEME):
        return _WS_SCHEME + base_url[len(_HTTP_SCHEME) :]
    return base_url


class WsTestClient:
    """
    Connects to Notification Service WebSocket.
    Collects all received messages.
    Use as async context manager.

    Usage:
        async with WsTestClient(url, token) as ws:
            # trigger some action
            await asyncio.sleep(2)
            msg = ws.find_message('notification.new')
            assert msg is not None
    """

    def __init__(self, base_url: str, user_id: str):
        ws_base_url = _to_ws_base_url(base_url)
        self.url = f"{ws_base_url}/ws/{user_id}"
        self.messages = []
        self._ws = None
        self._task = None

    async def __aenter__(self):
        self._ws = await websockets.connect(self.url)
        self._task = asyncio.create_task(self._receive_loop())
        return self

    async def __aexit__(self, *args):
        if self._task:
            self._task.cancel()
        if self._ws:
            await self._ws.close()

    async def _receive_loop(self):
        try:
            async for raw in self._ws:
                self.messages.append(json.loads(raw))
        except (websockets.ConnectionClosed, asyncio.CancelledError):
            pass

    def find_message(self, event: str) -> Optional[dict]:
        """Find first message matching event type."""
        return next((m for m in self.messages if m.get("event") == event), None)

    def all_messages(self, event: str) -> list[dict]:
        return [m for m in self.messages if m.get("event") == event]

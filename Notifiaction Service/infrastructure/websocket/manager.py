from collections import defaultdict
from typing import DefaultDict

from fastapi import WebSocket


class NotificationConnectionManager:
    def __init__(self):
        self._user_connections: DefaultDict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self._user_connections[user_id].add(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self._user_connections:
            self._user_connections[user_id].discard(websocket)
            if not self._user_connections[user_id]:
                self._user_connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, payload: dict):
        stale = []
        for ws in self._user_connections.get(user_id, set()):
            try:
                await ws.send_json(payload)
            except Exception:
                stale.append(ws)

        for ws in stale:
            self.disconnect(user_id, ws)

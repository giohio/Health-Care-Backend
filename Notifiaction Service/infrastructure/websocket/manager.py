from collections import defaultdict
from typing import DefaultDict
from uuid import UUID

from fastapi import WebSocket


class NotificationConnectionManager:
    def __init__(self):
        self._user_connections: DefaultDict[str, set[WebSocket]] = defaultdict(set)
        self._pending_payloads: DefaultDict[str, list[dict]] = defaultdict(list)

    @staticmethod
    def _normalize_user_id(user_id: str) -> str:
        raw = str(user_id).strip()
        try:
            return str(UUID(raw))
        except Exception:
            return raw.lower()

    async def connect(self, user_id: str, websocket: WebSocket):
        normalized_user_id = self._normalize_user_id(user_id)
        await websocket.accept()
        self._user_connections[normalized_user_id].add(websocket)
        await websocket.send_json(
            {
                "event": "connected",
                "data": {
                    "user_id": normalized_user_id,
                    "unread_count": 0,
                },
            }
        )

        # Flush notifications queued before this websocket was connected.
        queued = self._pending_payloads.pop(normalized_user_id, [])
        for payload in queued:
            try:
                await websocket.send_json(payload)
            except Exception:
                # Put back remaining payloads so they can be delivered next connect.
                self._pending_payloads[normalized_user_id].append(payload)
                break

    def disconnect(self, user_id: str, websocket: WebSocket):
        normalized_user_id = self._normalize_user_id(user_id)
        if normalized_user_id in self._user_connections:
            self._user_connections[normalized_user_id].discard(websocket)
            if not self._user_connections[normalized_user_id]:
                self._user_connections.pop(normalized_user_id, None)

    async def send_to_user(self, user_id: str, payload: dict):
        normalized_user_id = self._normalize_user_id(user_id)
        connections = self._user_connections.get(normalized_user_id, set())
        if not connections:
            self._pending_payloads[normalized_user_id].append(payload)
            return

        stale = []
        for ws in connections:
            try:
                await ws.send_json(payload)
            except Exception:
                stale.append(ws)

        for ws in stale:
            self.disconnect(normalized_user_id, ws)

        if len(stale) == len(connections):
            self._pending_payloads[normalized_user_id].append(payload)


# Explicit singleton shared by API routes and background consumers.
notification_ws_manager = NotificationConnectionManager()

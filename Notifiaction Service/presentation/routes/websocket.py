from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from infrastructure.websocket.manager import NotificationConnectionManager
from presentation.dependencies import get_ws_manager


router = APIRouter(tags=["Notifications"])


@router.websocket("/ws/{user_id}")
async def notifications_ws(
    websocket: WebSocket,
    user_id: str,
    ws_manager: Annotated[NotificationConnectionManager, Depends(get_ws_manager)],
):
    await ws_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(user_id, websocket)

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from app.core.websockets import manager
from app.api.deps import get_current_user_ws
import asyncio

router = APIRouter()

@router.websocket("/messages")
async def websocket_messages_endpoint(websocket: WebSocket):
    protocols = websocket.scope.get("subprotocols", [])
    if len(protocols) != 2 or protocols[0] != "emr-auth":
        await websocket.close(code=1008)
        return
    token = protocols[1]
    user = await get_current_user_ws(token)
    if not user:
        await websocket.close(code=1008)
        return

    await manager.connect(websocket, user.id, token)
    try:
        while True:
            # We just need to keep the connection open.
            # Client doesn't need to send anything over WS, it uses REST to send messages.
            # But we can listen for pings or incoming WS messages just in case.
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=15)
            except asyncio.TimeoutError:
                pass
            if not await get_current_user_ws(token):
                await websocket.close(code=1008)
                break
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, user.id)

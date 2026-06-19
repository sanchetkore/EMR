from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from app.core.websockets import manager
from app.api.deps import get_current_user_ws

router = APIRouter()

@router.websocket("/messages")
async def websocket_messages_endpoint(websocket: WebSocket, token: str):
    print(f"WS Connection attempt with token: {token[:10]}...")
    user = await get_current_user_ws(token)
    if not user:
        print("WS Connection rejected: Invalid token or user not found")
        await websocket.close(code=1008)
        return

    print(f"WS Connection accepted for user: {user.username} (ID: {user.id})")
    await manager.connect(websocket, user.id)
    try:
        while True:
            # We just need to keep the connection open.
            # Client doesn't need to send anything over WS, it uses REST to send messages.
            # But we can listen for pings or incoming WS messages just in case.
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, user.id)

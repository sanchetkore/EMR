from fastapi import WebSocket
from typing import Dict, List

class ConnectionManager:
    def __init__(self):
        # Maps user_id to a list of active WebSocket connections
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self.tokens = {}

    async def connect(self, websocket: WebSocket, user_id: int, token: str):
        await websocket.accept(subprotocol="emr-auth")
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        self.tokens[websocket] = token

    def disconnect(self, websocket: WebSocket, user_id: int):
        self.tokens.pop(websocket, None)
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_personal_message(self, message: dict, user_id: int):
        """Send a JSON message to all active connections of a specific user."""
        if user_id in self.active_connections:
            for connection in list(self.active_connections[user_id]):
                try:
                    from app.api.deps import get_current_user_ws
                    if not await get_current_user_ws(self.tokens.get(connection, "")):
                        await connection.close(code=1008)
                        self.disconnect(connection, user_id)
                        continue
                    await connection.send_json(message)
                except Exception:
                    self.disconnect(connection, user_id)

manager = ConnectionManager()

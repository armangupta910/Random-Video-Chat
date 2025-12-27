from typing import Dict
from fastapi import WebSocket
import asyncio

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.lock = asyncio.Lock()

    async def connect(self, name: str, websocket: WebSocket):
        await websocket.accept()
        async with self.lock:
            self.active_connections[name] = websocket

    async def disconnect(self, name: str):
        async with self.lock:
            self.active_connections.pop(name, None)

    async def send(self, name: str, message: dict):
        websocket = self.active_connections.get(name)
        if websocket:
            await websocket.send_json(message)

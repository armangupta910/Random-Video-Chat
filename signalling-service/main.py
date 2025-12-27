from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import redis
import json
from models import SignalMessage
from websocket_manager import ws_manager
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

origins = [
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis connection (from first MS)
REDIS_URL = "redis://127.0.0.1:6379"
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

def verify_room_and_role(room_code: str, user: str, peer: str, is_initiator_attempt: bool) -> bool:
    key = f"room:{room_code}"
    if not redis_client.exists(key):
        print("key doesnot exist")
        return False

    user_role = redis_client.hget(key, user)
    peer_role = redis_client.hget(key, peer)

    print("User Role - " + user_role + " Peer Role - " + peer_role)

    if not user_role or not peer_role:
        return False

    return True

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await ws_manager.connect(username, websocket)

    try:
        while True:
            msg = await websocket.receive_json()
            signal = SignalMessage(**msg)

            # Handle join request
            if signal.event == "join":
                # Check initiator only when starting connection
                is_initiator = True if signal.type == "offer" else False
                if not verify_room_and_role(signal.room_code, username, signal.target, is_initiator):
                    await websocket.send_json({"event": "error", "message": "Invalid room or role"})
                    continue
                key = f"room:{signal.room_code}"
                user_role = redis_client.hget(key, username)
                await websocket.send_json({
                    "event": "verified",
                    "room_code": signal.room_code,
                    "role": user_role
                })

            # Handle signaling messages
            elif signal.event == "signal":
                target_ws = ws_manager.active_connections.get(signal.target)
                if not target_ws:
                    await websocket.send_json({"event": "error", "message": "Peer not connected"})
                    continue

                # Forward message to peer
                await ws_manager.send(signal.target, {
                    "event": "signal",
                    "room_code": signal.room_code,
                    "from": username,
                    "type": signal.type,
                    "data": signal.data
                })

    except WebSocketDisconnect:
        await ws_manager.disconnect(username)
        # Notify peers (optional)
        # Could publish 'peer-disconnected' message if needed
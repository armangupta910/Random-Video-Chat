from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from models import User
import redis, os, json, time, asyncio, uuid
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from websocket_manager import WebSocketManager
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

origins = [
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
MATCH_QUEUE = "matching_queue"
INITIAL_BACKOFF = 0.01      # seconds
MAX_BACKOFF = 5.0          # seconds
BACKOFF_MULTIPLIER = 1
post_match_executor = ThreadPoolExecutor(max_workers=10)

ws_manager = WebSocketManager()

def run_async_task(coro):
    asyncio.run(coro)

def store_room(room_code: str, initiator: str, responder: str):
    key = f"room:{room_code}"

    redis_client.hset(key, mapping={
        initiator: "initiator",
        responder: "responder"
    })

    redis_client.expire(key, 300)

    # Store reverse mapping: user -> room_code
    redis_client.set(f"user_room:{initiator}", room_code, ex=300)
    redis_client.set(f"user_room:{responder}", room_code, ex=300)


async def handle_post_match(username1, username2):

    # WebSocket calls (async)
    room_code = username1 + "_" + username2
    store_room(room_code, username1, username2)

    await ws_manager.send(username1, {
        "event": "matched",
        "room_code": room_code,
        "initiator": True
    })

    await ws_manager.send(username2, {
        "event": "matched",
        "room_code": room_code,
        "initiator": False
    })

    print(f"Matched {username1} <-> {username2}")

def match_worker():
    backoff = INITIAL_BACKOFF

    while True:
        queue_size = redis_client.zcard(MATCH_QUEUE)

        # Not enough users → backoff
        if queue_size < 2:
            time.sleep(backoff)
            backoff = min(backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF)
            continue
        
        users = redis_client.zpopmin(MATCH_QUEUE, 2)
        username1 = users[0][0]
        username2 = users[1][0]

        backoff = INITIAL_BACKOFF

        print("Matched, socket for users :- ")
        for i in ws_manager.get_all_sockets():
            print(i)

        post_match_executor.submit(
            run_async_task,
            handle_post_match(username1, username2)
        )


async def handle_skip(username: str):
    # Remove from active connections
    await ws_manager.disconnect(username)

    # Lookup room code directly
    room_code = redis_client.get(f"user_room:{username}")
    if not room_code:
        return  # user was not in any room

    key = f"room:{room_code}"
    room = redis_client.hgetall(key)

    # Notify peer(s)
    for peer_name in room:
        if peer_name != username:
            await ws_manager.send(peer_name, {
                "event": "peer-disconnected",
                "message": f"{username} has disconnected"
            })

    # Clean up
    redis_client.delete(key)
    redis_client.delete(f"user_room:{username}")
    for peer_name in room:
        redis_client.delete(f"user_room:{peer_name}")
    
'''
============= Startup =============
'''
@app.on_event("startup")
def start_matcher():
    Thread(target=match_worker, daemon=True).start()


'''
============= Socket =============
'''
@app.websocket("/ws/{name}")
async def websocket_endpoint(websocket: WebSocket, name: str):
    print("Trying to add socket for user - " + name)
    await ws_manager.connect(name, websocket)
    try:
        while True:
            received_message = await websocket.receive_text()
            
            # Parse incoming message
            try:
                data = json.loads(received_message)
                
                # Handle chat messages
                if data.get("event") == "chat":
                    peer_name = data.get("peer")
                    message = data.get("message", "")
                    
                    if peer_name and message:
                        # Send message directly to the peer
                        await ws_manager.send(peer_name, {
                            "event": "chat",
                            "sender": name,
                            "message": message,
                            "timestamp": time.time()
                        })
                        print(f"Chat: {name} → {peer_name}: {message}")
                            
            except json.JSONDecodeError:
                print(f"Invalid JSON from {name}: {received_message}")
            
    except WebSocketDisconnect:
        await ws_manager.disconnect(name)
        redis_client.zrem(MATCH_QUEUE, name)

'''
============= APIs =============
'''
@app.get("/")
async def root():
    return {"message": "This is matching server of omegle clone."}

@app.post("/registerForMatching")
async def register_for_matching(user: User):
    # Check if user already exists in queue
    existing_score = redis_client.zscore(MATCH_QUEUE, user.name)
    
    if existing_score is not None:
        # await handle_skip(user.name)
        # await ws_manager.disconnect(user.name)
        return {
            "status": "exists",
            "message": "Username already exists in queue"
        }
    
    try:
        timestamp = time.time()
        redis_client.zadd(MATCH_QUEUE, {user.name: timestamp})
        print("Added " + user.name + " to the Matching Queue")

        # await handle_skip(user.name)
        
        return {
            "status": "queued",
            "message": "User added to matching queue"
        }
    except Exception as e:
        print(f"Error registering user: {e}")
        return {
            "status": "error",
            "message": "Internal server error"
        }

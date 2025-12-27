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
    allow_origins=origins,
    allow_credentials=True,
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

    redis_client.expire(key)

    # Store reverse mapping: user -> room_code
    redis_client.set(f"user_room:{initiator}", room_code)
    redis_client.set(f"user_room:{responder}", room_code)


async def handle_post_match(user1_raw, user2_raw):
    user1 = json.loads(user1_raw)
    user2 = json.loads(user2_raw)

    # WebSocket calls (async)
    room_code = str(user1['name']) + "_" + str(user2['name'])
    store_room(room_code, user1["name"], user2["name"])

    await ws_manager.send(user1["name"], {
        "event": "matched",
        "room_code": room_code,
        "initiator": True
    })

    await ws_manager.send(user2["name"], {
        "event": "matched",
        "room_code": room_code,
        "initiator": False
    })

    print(f"Matched {user1['name']} <-> {user2['name']} in room {room_code}")

def match_worker():
    print("Matching Started")
    backoff = INITIAL_BACKOFF

    while True:
        queue_size = redis_client.llen(MATCH_QUEUE)

        # Not enough users → backoff
        if queue_size < 2:
            time.sleep(backoff)
            backoff = min(backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF)
            continue
        
        user1 = redis_client.lpop(MATCH_QUEUE)
        user2 = redis_client.lpop(MATCH_QUEUE)

        backoff = INITIAL_BACKOFF

        post_match_executor.submit(
            run_async_task,
            handle_post_match(user1, user2)
        )


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
    await ws_manager.connect(name, websocket)
    try:
        while True:
            # Keep connection alive (client may send pings)
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(name)


'''
============= APIs =============
'''
@app.get("/")
async def root():
    return {"message": "This is Omegle clone."}

@app.post("/registerForMatching")
async def register_for_matching(user: User):
    redis_client.rpush(MATCH_QUEUE, user.json())

    return {
        "status": "queued",
        "message": "User added to matching queue"
    }

from pydantic import BaseModel

class SignalMessage(BaseModel):
    event: str           # "join" or "signal"
    room_code: str
    target: str = None   # peer username (for signaling)
    type: str = None     # "offer", "answer", "candidate" (for signaling)
    data: dict = None    # actual SDP or ICE data

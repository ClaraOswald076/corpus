import json
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.meeting.message_bus import message_bus_registry
from src.meeting.protocol import meeting_protocol_registry

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self._connections: dict[uuid.UUID, list[WebSocket]] = {}

    async def connect(self, meeting_id: uuid.UUID, websocket: WebSocket):
        await websocket.accept()
        if meeting_id not in self._connections:
            self._connections[meeting_id] = []
        self._connections[meeting_id].append(websocket)

    def disconnect(self, meeting_id: uuid.UUID, websocket: WebSocket):
        if meeting_id in self._connections:
            self._connections[meeting_id].remove(websocket)

    async def broadcast(self, meeting_id: uuid.UUID, data: dict):
        if meeting_id in self._connections:
            dead = []
            for ws in self._connections[meeting_id]:
                try:
                    await ws.send_json(data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.disconnect(meeting_id, ws)


manager = ConnectionManager()


@router.websocket("/{meeting_id}/live")
async def meeting_live(websocket: WebSocket, meeting_id: str):
    mid = uuid.UUID(meeting_id)

    engine = meeting_protocol_registry.get(mid)
    if not engine or not engine.bus:
        await websocket.close(code=4004, reason="会议未在进行中")
        return

    await manager.connect(mid, websocket)

    # Send current state
    await websocket.send_json({
        "type": "state",
        "data": engine.to_dict(),
        "history": [
            {"type": m.message_type.value, "sender": str(m.sender_agent_id),
             "content": m.content, "turn": m.turn_number}
            for m in engine.bus.get_recent(20)
        ],
    })

    # Subscribe to message bus for this viewer
    queue = await engine.bus.subscribe(uuid.uuid4())  # ephemeral viewer

    try:
        while True:
            # Read from message bus and forward
            msg = await queue.get()
            await websocket.send_json({
                "type": msg.message_type.value,
                "sender": str(msg.sender_agent_id),
                "content": msg.content,
                "turn": msg.turn_number,
                "metadata": msg.metadata,
                "timestamp": msg.timestamp.isoformat(),
            })
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(mid, websocket)
        await engine.bus.unsubscribe(uuid.uuid4())

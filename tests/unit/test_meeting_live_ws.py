import uuid
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.api.websocket.meeting_live import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_invalid_meeting_id_rejected_cleanly(client):
    # 非法 UUID 不应让 ValueError 穿透到 ASGI 层，而是干净拒绝握手
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/not-a-uuid/live"):
            pass
    assert exc_info.value.code == 1008


def test_unknown_meeting_id_still_gets_4004(client):
    # 合法但不存在的会议：既有设计路径保持不变
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/{uuid.uuid4()}/live"):
            pass
    assert exc_info.value.code == 4004

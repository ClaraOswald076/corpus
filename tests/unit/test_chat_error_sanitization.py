"""chat 失败响应的脱敏回归测试。

背景：#41——LLM 调用失败时 error_message（litellm/OpenAI SDK 的异常原文，含模型串、
密钥片段等内部信息）被原样塞进 500 detail 回显给客户端。
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.utils.llm_client import LLMCallResult


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _make_agent(client, tag: str) -> str:
    dept = client.post("/api/org/", json={
        "name": f"脱敏部-{tag}", "tier": 0, "dept_type": "ceo_office",
    }).json()["id"]
    client.post("/api/presets/", json={
        "name": f"脱敏预设-{tag}", "provider": "openai", "model_name": "gpt-4o",
        "litellm_model_string": "openai/gpt-4o",
    })
    r = client.post("/api/agents/", json={
        "name": f"脱敏员-{tag}", "role": "工程师", "department_id": dept,
        "preset_name": f"脱敏预设-{tag}",
    })
    return r.json()["id"]


def test_chat_failure_detail_is_sanitized(client, monkeypatch):
    tag = uuid.uuid4().hex[:6]
    _make_agent(client, tag)

    class _FailingAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def think(self, message, extra_instructions=""):
            return LLMCallResult(
                content="", model="openai/gpt-4o", prompt_tokens=0, completion_tokens=0,
                total_tokens=0, estimated_cost_usd=0.0, latency_ms=0, success=False,
                error_message="litellm.AuthenticationError: Error code: 401 - Your api key: sk-proj-SECRET",
            )

    monkeypatch.setattr("src.api.routes.chat.BaseAgent", _FailingAgent)
    r = client.post("/api/chat/", json={"agent_name": f"脱敏员-{tag}", "message": "你好"})
    assert r.status_code == 500
    detail = r.json()["detail"]
    assert "sk-proj-SECRET" not in detail
    assert "litellm" not in detail
    assert "LLM 调用失败" in detail

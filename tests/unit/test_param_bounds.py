"""数值参数边界的回归测试。

背景：#40——Agent/任务/预设端点对 max_retries/temperature/max_tokens 等不设界，
max_retries=9.9 亿会被 watchdog 与 LLM 重试循环当真，负数 max_tokens 让该 Agent
每次调用必败。校验在 pydantic 层完成，越界值应 422 且不落库。
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_retries": 999999999},
        {"max_retries": -1},
        {"temperature": 57.0},
        {"temperature": -0.1},
        {"max_tokens": -1},
        {"max_tokens": 0},
        {"max_memory_tokens": 0},
    ],
)
def test_agent_create_rejects_out_of_range_params(overrides):
    r = client.post("/api/agents/", json={"name": "x", "role": "y", **overrides})
    assert r.status_code == 422, f"{overrides} 应被 422 拒绝，实际 {r.status_code}"


@pytest.mark.parametrize(
    "overrides",
    [
        {"temperature": -3.0},
        {"max_tokens": -999},
        {"max_memory_tokens": 0},
    ],
)
def test_agent_update_rejects_out_of_range_params(overrides):
    # 校验发生在路由处理器之前，非法 uuid 不会被触达
    r = client.put("/api/agents/00000000-0000-0000-0000-000000000000", json=overrides)
    assert r.status_code == 422, f"{overrides} 应被 422 拒绝，实际 {r.status_code}"


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_retries": -3},
        {"max_retries": 1000000},
        {"timeout_seconds": 0},
        {"timeout_seconds": -5},
    ],
)
def test_task_create_rejects_out_of_range_params(overrides):
    r = client.post("/api/tasks/", json={"title": "x", **overrides})
    assert r.status_code == 422, f"{overrides} 应被 422 拒绝，实际 {r.status_code}"


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_retries": 99},
        {"retry_delay_sec": -1.0},
    ],
)
def test_preset_create_rejects_out_of_range_params(overrides):
    r = client.post("/api/presets/", json={"name": "x", "provider": "openai", "model_name": "m", **overrides})
    assert r.status_code == 422, f"{overrides} 应被 422 拒绝，实际 {r.status_code}"


def test_agent_accepts_boundary_values():
    tag = uuid.uuid4().hex[:6]
    with TestClient(app) as c:
        dept = c.post("/api/org/", json={"name": f"边界部-{tag}", "tier": 0, "dept_type": "ceo_office"}).json()["id"]
        r = c.post("/api/agents/", json={
            "name": f"边界员-{tag}", "role": "工程师", "department_id": dept,
            "max_retries": 10, "temperature": 2.0, "max_tokens": 1000000, "max_memory_tokens": 10000000,
        })
        assert r.status_code == 201, r.text
        got = c.get(f"/api/agents/{r.json()['id']}").json()
        assert got["temperature"] == 2.0
        assert got["max_tokens"] == 1000000
        assert got["max_memory_tokens"] == 10000000


def test_task_accepts_boundary_values():
    with TestClient(app) as c:
        r = c.post("/api/tasks/", json={"title": "边界任务", "max_retries": 10, "timeout_seconds": 2592000})
        assert r.status_code == 201, r.text
        assert r.json()["max_retries"] == 10

"""路由层异常分流回归测试：领域错误原样透传，内部异常只给固定话术。

对应 issue #44：路由层 except Exception 一把抓把内部异常报文回显进 400/404。

运行：python -m pytest tests/unit/test_route_error_handling.py -q
"""
import asyncio
import uuid
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api.app import app
from src.api.deps import get_db
from src.models.base import Base
from src.services.org_structure import OrgStructureService


async def _create_all(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture()
def client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'route-test.db'}", echo=False)
    asyncio.run(_create_all(engine))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _create_t0(client, name):
    r = client.post("/api/org/", json={"name": name, "tier": 0, "dept_type": "ceo_office"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_duplicate_department_no_sql_echo(client):
    # 部门名全局唯一且服务层无预检：重名必撞 IntegrityError，
    # 旧代码会把整段 SQL 与绑定参数回显进 400 detail
    t0 = _create_t0(client, "研发部")
    r = client.post("/api/org/", json={
        "name": "研发部", "tier": 1, "dept_type": "department", "parent_id": t0,
    })
    assert r.status_code == 400
    assert r.json()["detail"] == "部门名称或编码已被占用"
    for leak in ("INSERT", "SQL", "sqlalche.me", "parameters"):
        assert leak not in r.json()["detail"]


def test_malformed_uuid_fixed_message(client):
    # 旧代码回显 uuid 库原文 "badly formed hexadecimal UUID string"
    r = client.get("/api/agents/not-a-uuid")
    assert r.status_code == 404
    assert r.json()["detail"] == "请求参数格式无效"


def test_internal_error_returns_generic_500(client, monkeypatch, caplog):
    # 模拟服务层内部故障：必须 500 固定话术 + 服务端留全量堆栈，不回显异常内容
    async def boom(self, department_id):
        raise RuntimeError("连接池耗尽 secret-detail")

    monkeypatch.setattr(OrgStructureService, "get_department", boom)
    with caplog.at_level(logging.ERROR, logger="src.api.routes.organizations"):
        r = client.get(f"/api/org/{uuid.uuid4()}")
    assert r.status_code == 500
    assert r.json()["detail"] == "服务器内部错误，请稍后重试"
    assert "RuntimeError" not in r.json()["detail"]
    assert "secret-detail" not in r.json()["detail"]
    assert any("organizations 路由内部错误" in rec.message and rec.exc_info for rec in caplog.records)


def test_domain_error_passes_through(client):
    # 领域异常通道不受影响：重名预设仍是业务话术
    # （不带 api_key_plaintext，避开 FERNET_KEY 依赖；重名预检在加密之前触发）
    payload = {"name": "默认预设", "provider": "deepseek", "model_name": "deepseek-chat"}
    assert client.post("/api/presets/", json=payload).status_code == 201
    r = client.post("/api/presets/", json=payload)
    assert r.status_code == 400
    assert "已存在" in r.json()["detail"]


def test_http_exception_not_double_wrapped(client):
    # try 块内主动 raise 的 HTTPException 不再被 except Exception 二次包成 "400: ..." 前缀话术
    r = client.post("/api/agents/", json={"name": "小助手", "role": "文员"})
    assert r.status_code == 400
    assert r.json()["detail"] == "部门不能为空"

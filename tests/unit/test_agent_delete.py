"""Agent 删除回归测试：带灵魂文档的 agent 必须能整体删除，不留幽灵。

对应 issue #46：旧实现先删目录后删库，且 soul_document 无 ORM 级联，
删 Agent 行前 ORM 先把 soul_documents.agent_id 置 NULL 撞 non-null 约束，
目录已删、行还在，形成永久幽灵。

运行：python -m pytest tests/unit/test_agent_delete.py -q
"""
from pathlib import Path

import pytest
from sqlalchemy import select

import src.services.agent_lifecycle as agent_lifecycle_module
from src.core.exceptions import AgentNotFoundError
from src.models.agent import SoulDocument
from src.models.organization import Agent, Department
from src.services.agent_lifecycle import AgentLifecycleService, AgentCreate


@pytest.fixture
def fs_root(tmp_path, monkeypatch):
    # 把 agent 目录根指到临时目录，文件夹断言不污染仓库
    monkeypatch.setattr(agent_lifecycle_module.settings, "project_root", tmp_path)
    monkeypatch.setattr(agent_lifecycle_module.settings, "agents_root", tmp_path / "agents")
    return tmp_path


async def _make_agent(db_session, fs_root, name="ghost_agent", soul="我的灵魂"):
    # 先 commit 建好的 agent，模拟真实请求流：后续回滚只回滚删除这一笔
    dept = Department(name=f"研发部-{name}", org_path=f"/rd/{name}", tier=2, dept_type="department")
    db_session.add(dept)
    await db_session.flush()
    svc = AgentLifecycleService(db_session)
    agent = await svc.create_agent(AgentCreate(
        name=name, role="工程师", department_id=dept.id, soul_content=soul,
    ))
    await db_session.commit()
    folder = Path(agent.agent_folder_path)
    return svc, agent, folder


@pytest.mark.asyncio
async def test_delete_agent_with_soul_document_succeeds(db_session, fs_root):
    # 删除带灵魂文档的 agent：agent 行、soul 行、磁盘目录都要一起消失
    svc, agent, folder = await _make_agent(db_session, fs_root)
    assert (fs_root / folder).exists()
    soul = await db_session.scalar(select(SoulDocument).where(SoulDocument.agent_id == agent.id))
    assert soul is not None

    await svc.delete_agent(agent.id)
    await db_session.commit()

    assert await db_session.get(Agent, agent.id) is None
    remaining = await db_session.scalar(select(SoulDocument).where(SoulDocument.agent_id == agent.id))
    assert remaining is None
    assert not (fs_root / folder).exists()


@pytest.mark.asyncio
async def test_delete_agent_allows_name_reuse(db_session, fs_root):
    # 删除后同一名可重建：旧实现留下幽灵行会让重建撞"已存在"
    svc, agent, _ = await _make_agent(db_session, fs_root, name="reuse_agent")
    dept_id = agent.department_id
    await svc.delete_agent(agent.id)
    await db_session.commit()

    svc2 = AgentLifecycleService(db_session)
    recreated = await svc2.create_agent(AgentCreate(
        name="reuse_agent", role="工程师", department_id=dept_id,
    ))
    await db_session.commit()
    assert recreated.name == "reuse_agent"


@pytest.mark.asyncio
async def test_delete_agent_folder_failure_keeps_row(db_session, fs_root, monkeypatch):
    # 目录删除失败：异常上抛、agent 行保留（路由层回滚后行与目录都在，可重试）
    svc, agent, folder = await _make_agent(db_session, fs_root, name="fs_fail_agent")
    agent_id = agent.id  # rollback 会把 ORM 对象置过期，先取 id

    def boom(path):
        raise RuntimeError(f"模拟目录删除失败: {path}")

    monkeypatch.setattr(agent_lifecycle_module, "delete_agent_folder", boom)
    with pytest.raises(RuntimeError):
        await svc.delete_agent(agent_id)
    await db_session.rollback()

    assert await db_session.get(Agent, agent_id) is not None
    assert (fs_root / folder).exists()


@pytest.mark.asyncio
async def test_delete_missing_agent_raises_not_found(db_session, fs_root):
    import uuid
    svc = AgentLifecycleService(db_session)
    with pytest.raises(AgentNotFoundError):
        await svc.delete_agent(uuid.uuid4())

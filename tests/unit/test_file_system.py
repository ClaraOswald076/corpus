from pathlib import Path

import pytest

from src.core.config import settings
from src.core.exceptions import PlatformError
from src.utils.file_system import (
    create_agent_folder,
    delete_agent_folder,
    get_agent_folder_path,
)


def test_malicious_names_cannot_escape_agents_root():
    # 名称里的路径分隔符与 .. 必须被 slug 折叠，不得产生 agents_root 之外的路径
    folder = get_agent_folder_path("..\\..\\evil", "..\\..\\escape")
    resolved = folder.resolve()
    root = settings.agents_root.resolve()
    assert root == resolved or root in resolved.parents
    assert ".." not in folder.parts


def test_normal_names_keep_readable_slugs():
    # 原有行为保留：空格与 / 折叠为 _，中文与字母数字不变
    assert get_agent_folder_path("CEO办公室", "张三").name == "张三"
    folder = get_agent_folder_path("Product Dept", "Dev Bot")
    assert folder.parent.name == "product_dept"
    assert folder.name == "dev_bot"
    assert get_agent_folder_path("研发部", "a/b").name == "a_b"


def test_create_and_delete_agent_folder_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "agents_root", tmp_path / "agents")
    folder = create_agent_folder("CEO办公室", "测试Agent", soul_content="s", memory_content="m")
    assert (folder / "soul.md").exists()
    assert (folder / "memory.md").exists()
    delete_agent_folder(str(folder))
    assert not folder.exists()


def test_delete_refuses_traversal_path_stored_in_db(tmp_path, monkeypatch):
    # 兜底：库里若存有带 .. 的历史脏路径，删除必须被拒绝而不是 rmtree 逃逸目录
    monkeypatch.setattr(settings, "agents_root", tmp_path / "agents")
    evil = str(settings.agents_root / "dept" / ".." / ".." / "outside")
    with pytest.raises(PlatformError):
        delete_agent_folder(evil)


def test_delete_refuses_paths_outside_agents_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "agents_root", tmp_path / "agents")
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(PlatformError):
        delete_agent_folder(str(outside))

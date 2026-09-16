import os
import re
from datetime import datetime, timezone
from pathlib import Path
from src.core.config import settings
from src.core.exceptions import PlatformError

# slug 只保留字母/数字/下划线/连字符，路径分隔符与 .. 一律折叠成 _，防止目录逃逸
_SLUG_UNSAFE = re.compile(r"[^\w-]+", re.UNICODE)


def _slugify(name: str) -> str:
    return _SLUG_UNSAFE.sub("_", name.lower()).strip("_") or "unnamed"


def _ensure_within_agents_root(folder: Path):
    resolved = folder.resolve()
    root = settings.agents_root.resolve()
    if resolved != root and root not in resolved.parents:
        raise PlatformError(f"agent 目录越界，拒绝操作: {resolved}")


def get_agent_folder_path(department_name: str, agent_name: str) -> Path:
    dept_slug = _slugify(department_name)
    agent_slug = _slugify(agent_name)
    return settings.agents_root / dept_slug / agent_slug


def create_agent_folder(department_name: str, agent_name: str, soul_content: str = "", memory_content: str = "") -> Path:
    folder = get_agent_folder_path(department_name, agent_name)
    _ensure_within_agents_root(folder)
    folder.mkdir(parents=True, exist_ok=True)
    workspace = folder / settings.workspace_dir_name
    workspace.mkdir(exist_ok=True)

    soul_path = folder / settings.soul_filename
    if not soul_path.exists():
        default_soul = f"# {agent_name} - Soul Document\n\n## 角色定位\n\n{soul_content or '待定义'}\n\n## 核心能力\n\n待定义\n\n## 协作接口\n\n待定义\n\n## 人格与约束\n\n你是AI Agent，处理速度远超人类。\n\n---\n创建时间: {datetime.now(timezone.utc).isoformat()}\n"
        soul_path.write_text(default_soul, encoding="utf-8")

    memory_path = folder / settings.memory_filename
    if not memory_path.exists():
        default_memory = f"# {agent_name} - Memory\n\n## 重要经验\n\n{memory_content or '(尚无记忆)'}\n\n---\n创建时间: {datetime.now(timezone.utc).isoformat()}\n"
        memory_path.write_text(default_memory, encoding="utf-8")

    return folder


def read_agent_soul(agent_folder_path: str) -> str:
    path = Path(agent_folder_path) / settings.soul_filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def write_agent_soul(agent_folder_path: str, content: str):
    path = Path(agent_folder_path) / settings.soul_filename
    path.write_text(content, encoding="utf-8")


def read_agent_memory(agent_folder_path: str) -> str:
    path = Path(agent_folder_path) / settings.memory_filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def write_agent_memory(agent_folder_path: str, content: str):
    path = Path(agent_folder_path) / settings.memory_filename
    path.write_text(content, encoding="utf-8")


def append_agent_memory(agent_folder_path: str, entry: str):
    path = Path(agent_folder_path) / settings.memory_filename
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n\n[{timestamp}]\n{entry}\n")


def get_soul_last_modified(agent_folder_path: str) -> datetime | None:
    path = Path(agent_folder_path) / settings.soul_filename
    if path.exists():
        mtime = os.path.getmtime(str(path))
        return datetime.fromtimestamp(mtime, tz=timezone.utc)
    return None


def delete_agent_folder(agent_folder_path: str):
    import shutil
    path = Path(agent_folder_path)
    _ensure_within_agents_root(path)
    if path.exists():
        shutil.rmtree(path)

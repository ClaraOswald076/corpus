from datetime import datetime, timezone


def generate_task_code(root_code: str | None = None, depth: int = 0) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    if root_code is None:
        from src.repositories.task_repo import TaskRepository
        return f"T-{today}-001"
    parts = root_code.split("-")
    if depth == 0:
        base = "-".join(parts[:3])
        return f"{base}-001"
    else:
        return f"{root_code}-{depth + 1:03d}"


def generate_meeting_code() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"MTG-{today}-001"


def generate_recruitment_code() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"RC-{today}-001"

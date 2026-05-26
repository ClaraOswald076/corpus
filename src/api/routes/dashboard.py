from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pathlib import Path

router = APIRouter()

DASHBOARD_PATH = Path(__file__).parent.parent.parent.parent / "dashboard.html"


@router.get("/", response_class=HTMLResponse)
async def get_dashboard():
    if DASHBOARD_PATH.exists():
        return DASHBOARD_PATH.read_text(encoding="utf-8")
    return "<h1>dashboard.html not found</h1>"

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.core.config import settings
from src.core.database import init_db
from src.api.routes import organizations, agents, presets, tasks, meetings, escalations, dashboard, chat
from src.api.websocket import meeting_live


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    from src.workers.scheduler import scheduler
    await scheduler.start_all()
    yield
    await scheduler.stop_all()


app = FastAPI(
    title=settings.platform_name,
    description="多智能体层级平台 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(organizations.router, prefix="/api/org", tags=["组织架构"])
app.include_router(agents.router, prefix="/api/agents", tags=["Agent管理"])
app.include_router(presets.router, prefix="/api/presets", tags=["模型预设"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["任务管理"])
app.include_router(meetings.router, prefix="/api/meetings", tags=["会议管理"])
app.include_router(escalations.router, prefix="/api/escalations", tags=["升级管理"])
app.include_router(chat.router, prefix="/api/chat", tags=["对话"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["面板"])
app.include_router(meeting_live.router, prefix="/ws")


@app.get("/api/health")
async def health():
    return {"status": "ok", "platform": settings.platform_name}

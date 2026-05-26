import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from src.api.deps import get_db
from src.services.escalation_engine import EscalationEngine, EscalationReason, EscalationResolution

router = APIRouter()


class EscalationResolveRequest(BaseModel):
    resolution: str
    resolved_by_agent_id: str
    notes: str = ""


@router.get("/")
async def list_escalations(task_id: str | None = None, agent_id: str | None = None, db: AsyncSession = Depends(get_db)):
    engine = EscalationEngine(db)
    events = await engine.get_escalations(
        task_id=uuid.UUID(task_id) if task_id else None,
        agent_id=uuid.UUID(agent_id) if agent_id else None,
    )
    return [_event_to_dict(e) for e in events]


@router.get("/pending")
async def list_pending(agent_id: str | None = None, db: AsyncSession = Depends(get_db)):
    engine = EscalationEngine(db)
    events = await engine.get_pending_escalations(
        agent_id=uuid.UUID(agent_id) if agent_id else None,
    )
    return [_event_to_dict(e) for e in events]


@router.post("/{task_id}/escalate")
async def escalate_task(task_id: str, reason: str = "max_retries_exceeded", db: AsyncSession = Depends(get_db)):
    engine = EscalationEngine(db)
    try:
        event = await engine.escalate(uuid.UUID(task_id), EscalationReason(reason))
        await db.commit()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {**_event_to_dict(event), "message": "已升级"}


@router.post("/{task_id}/analyze")
async def analyze_task(task_id: str, db: AsyncSession = Depends(get_db)):
    engine = EscalationEngine(db)
    analysis = await engine.analyze_failure(uuid.UUID(task_id))
    if not analysis:
        raise HTTPException(status_code=400, detail="任务不需要升级分析")
    return {
        "task_id": str(analysis.task_id),
        "task_code": analysis.task_code,
        "reason": analysis.reason.value,
        "error_detail": analysis.error_detail,
        "retry_count": analysis.retry_count,
        "max_retries": analysis.max_retries,
        "assigned_agent_name": analysis.assigned_agent_name,
    }


@router.put("/{escalation_id}/resolve")
async def resolve_escalation(escalation_id: str, data: EscalationResolveRequest, db: AsyncSession = Depends(get_db)):
    engine = EscalationEngine(db)
    try:
        event = await engine.resolve_escalation(
            uuid.UUID(escalation_id),
            EscalationResolution(data.resolution),
            uuid.UUID(data.resolved_by_agent_id),
            data.notes,
        )
        await db.commit()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {**_event_to_dict(event), "message": f"升级已解决: {event.resolution}"}


@router.get("/{escalation_id}")
async def get_escalation(escalation_id: str, db: AsyncSession = Depends(get_db)):
    event = await db.get(__import__("src.models.escalation").EscalationEvent, uuid.UUID(escalation_id))
    if not event:
        raise HTTPException(status_code=404, detail="升级事件不存在")
    return _event_to_dict(event)


def _event_to_dict(event) -> dict:
    return {
        "id": str(event.id),
        "task_id": str(event.task_id),
        "from_agent_id": str(event.from_agent_id),
        "to_agent_id": str(event.to_agent_id),
        "escalation_level": event.escalation_level,
        "reason": event.reason,
        "resolution": event.resolution,
        "resolution_notes": event.resolution_notes,
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "resolved_at": event.resolved_at.isoformat() if event.resolved_at else None,
    }

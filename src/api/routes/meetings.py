import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from src.api.deps import get_db
from src.services.meeting_orchestrator import MeetingOrchestrator, MeetingCreate
from src.meeting.types import MeetingType, MeetingStatus
from src.meeting.protocol import meeting_protocol_registry

router = APIRouter()


class MeetingCreateRequest(BaseModel):
    meeting_type: str = "coordination"
    title: str
    secretary_agent_id: str = ""
    secretary_name: str = ""  # Alternative: resolve by name
    agenda: str = ""
    chair_agent_id: str | None = None
    chair_name: str = ""  # Alternative: resolve by name
    participant_agent_ids: list[str] = []
    participants: str = ""  # Alternative: comma-separated names
    max_turns: int | None = None


class StatementRequest(BaseModel):
    speaker_agent_id: str
    content: str
    statement_type: str = "general"
    reply_to_statement_id: str | None = None
    token_count: int | None = None


class MinutesRequest(BaseModel):
    content: str
    summary: str = ""
    action_items: list = []
    decisions: list = []
    generated_by_agent_id: str


class RequestToSpeakRequest(BaseModel):
    agent_id: str
    agent_name: str
    urgency: int = 5
    topic_relevance: float = 0.5
    reference: str = ""


@router.get("/")
async def list_meetings(status: str | None = None, db: AsyncSession = Depends(get_db)):
    svc = MeetingOrchestrator(db)
    meetings = await svc.list_meetings(status=status)
    return [_meeting_to_dict(m) for m in meetings]


@router.post("/", status_code=201)
async def create_meeting(data: MeetingCreateRequest, db: AsyncSession = Depends(get_db)):
    svc = MeetingOrchestrator(db)
    try:
        from src.repositories.agent_repo import AgentRepository
        agent_repo = AgentRepository(db)

        # Resolve secretary
        secretary_id = None
        if data.secretary_agent_id:
            secretary_id = uuid.UUID(data.secretary_agent_id)
        elif data.secretary_name:
            a = await agent_repo.get_by_name(data.secretary_name)
            if a: secretary_id = a.id
        if not secretary_id:
            raise HTTPException(status_code=400, detail="秘书Agent不能为空")

        # Resolve chair
        chair_id = None
        if data.chair_agent_id:
            chair_id = uuid.UUID(data.chair_agent_id)
        elif data.chair_name:
            a = await agent_repo.get_by_name(data.chair_name)
            if a: chair_id = a.id

        # Resolve participants
        participant_ids = [uuid.UUID(pid) for pid in data.participant_agent_ids]
        if data.participants:
            for name in data.participants.split(","):
                name = name.strip()
                if name:
                    a = await agent_repo.get_by_name(name)
                    if a and a.id not in participant_ids:
                        participant_ids.append(a.id)

        meeting = await svc.create_meeting(MeetingCreate(
            meeting_type=MeetingType(data.meeting_type),
            title=data.title,
            secretary_agent_id=secretary_id,
            agenda=data.agenda,
            chair_agent_id=chair_id,
            participant_agent_ids=participant_ids,
            max_turns=data.max_turns,
        ))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {**_meeting_to_dict(meeting), "message": "会议已创建"}


@router.get("/active")
async def list_active_meetings():
    engines = meeting_protocol_registry._engines
    return {
        "active_count": len(engines),
        "meetings": [
            {"meeting_id": str(mid), **eng.to_dict()}
            for mid, eng in engines.items()
        ],
    }


@router.get("/{meeting_id}")
async def get_meeting(meeting_id: str, db: AsyncSession = Depends(get_db)):
    svc = MeetingOrchestrator(db)
    try:
        meeting = await svc.get_meeting(uuid.UUID(meeting_id))
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    result = _meeting_to_dict(meeting)
    participants = await svc.get_participants(meeting.id)
    result["participants"] = [
        {"agent_id": str(p.agent_id), "role": p.role, "is_required": p.is_required}
        for p in participants
    ]
    engine = meeting_protocol_registry.get(meeting.id)
    if engine:
        result["live"] = engine.to_dict()
    else:
        result["live"] = None
    return result


@router.post("/{meeting_id}/start")
async def start_meeting(meeting_id: str, db: AsyncSession = Depends(get_db)):
    svc = MeetingOrchestrator(db)
    try:
        engine = await svc.start_meeting(uuid.UUID(meeting_id))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"meeting_id": meeting_id, "status": "in_progress", "live": engine.to_dict()}


@router.post("/{meeting_id}/end")
async def end_meeting(meeting_id: str, db: AsyncSession = Depends(get_db)):
    svc = MeetingOrchestrator(db)
    try:
        meeting = await svc.end_meeting(uuid.UUID(meeting_id))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"meeting_id": meeting_id, "status": meeting.status, "message": "会议已休会"}


@router.post("/{meeting_id}/cancel")
async def cancel_meeting(meeting_id: str, db: AsyncSession = Depends(get_db)):
    svc = MeetingOrchestrator(db)
    try:
        meeting = await svc.cancel_meeting(uuid.UUID(meeting_id))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"meeting_id": meeting_id, "status": meeting.status, "message": "会议已取消"}


@router.post("/{meeting_id}/complete")
async def complete_meeting(meeting_id: str, db: AsyncSession = Depends(get_db)):
    svc = MeetingOrchestrator(db)
    try:
        meeting = await svc.complete_meeting(uuid.UUID(meeting_id))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"meeting_id": meeting_id, "status": meeting.status, "message": "会议已完成"}


@router.post("/{meeting_id}/request-speak")
async def request_to_speak(meeting_id: str, data: RequestToSpeakRequest, db: AsyncSession = Depends(get_db)):
    engine = meeting_protocol_registry.get(uuid.UUID(meeting_id))
    if not engine:
        raise HTTPException(status_code=400, detail="会议未在进行中")
    await engine.submit_request_to_speak(
        uuid.UUID(data.agent_id), data.agent_name,
        data.urgency, data.topic_relevance, data.reference,
    )
    return {"message": f"{data.agent_name} 已加入发言队列", "queue_length": engine.speaker_queue.pending_count}


@router.post("/{meeting_id}/grant-next")
async def grant_next_speaker(meeting_id: str, db: AsyncSession = Depends(get_db)):
    engine = meeting_protocol_registry.get(uuid.UUID(meeting_id))
    if not engine:
        raise HTTPException(status_code=400, detail="会议未在进行中")
    next_speaker = await engine.grant_next_speaker()
    if not next_speaker:
        return {"message": "无待发言请求", "next_speaker": None}
    return {"next_speaker": str(next_speaker), "turn_number": engine.turn_count}


@router.post("/{meeting_id}/statements")
async def add_statement(meeting_id: str, data: StatementRequest, db: AsyncSession = Depends(get_db)):
    svc = MeetingOrchestrator(db)
    try:
        stmt = await svc.add_statement(
            uuid.UUID(meeting_id), uuid.UUID(data.speaker_agent_id),
            data.content, data.statement_type,
            uuid.UUID(data.reply_to_statement_id) if data.reply_to_statement_id else None,
            data.token_count,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": str(stmt.id), "content": stmt.content[:100] + "...", "message": "发言已记录"}


@router.get("/{meeting_id}/statements")
async def get_statements(meeting_id: str, db: AsyncSession = Depends(get_db)):
    svc = MeetingOrchestrator(db)
    statements = await svc.get_statements(uuid.UUID(meeting_id))
    return [
        {"id": str(s.id), "speaker": str(s.speaker_agent_id), "content": s.content,
         "type": s.statement_type, "turn": str(s.turn_id) if s.turn_id else None,
         "created_at": s.created_at.isoformat()}
        for s in statements
    ]


@router.post("/{meeting_id}/minutes")
async def save_minutes(meeting_id: str, data: MinutesRequest, db: AsyncSession = Depends(get_db)):
    svc = MeetingOrchestrator(db)
    try:
        minutes = await svc.save_minutes(
            uuid.UUID(meeting_id), data.content, data.summary,
            data.action_items, data.decisions,
            uuid.UUID(data.generated_by_agent_id),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": str(minutes.id), "version": minutes.version, "message": "纪要已保存"}


@router.get("/{meeting_id}/minutes")
async def get_minutes(meeting_id: str, db: AsyncSession = Depends(get_db)):
    svc = MeetingOrchestrator(db)
    minutes = await svc.get_minutes(uuid.UUID(meeting_id))
    if not minutes:
        raise HTTPException(status_code=404, detail="会议纪要尚未生成")
    return {
        "id": str(minutes.id), "content": minutes.content, "summary": minutes.summary,
        "action_items": minutes.action_items, "decisions": minutes.decisions,
        "version": minutes.version,
    }


@router.get("/{meeting_id}/live-state")
async def get_live_state(meeting_id: str):
    engine = meeting_protocol_registry.get(uuid.UUID(meeting_id))
    if not engine:
        raise HTTPException(status_code=404, detail="会议未在进行中")
    return engine.to_dict()


def _meeting_to_dict(meeting) -> dict:
    return {
        "id": str(meeting.id),
        "meeting_code": meeting.meeting_code,
        "meeting_type": meeting.meeting_type,
        "title": meeting.title,
        "status": meeting.status,
        "chair_agent_id": str(meeting.chair_agent_id) if meeting.chair_agent_id else None,
        "secretary_agent_id": str(meeting.secretary_agent_id),
        "max_turns": meeting.max_turns,
        "started_at": meeting.started_at.isoformat() if meeting.started_at else None,
        "ended_at": meeting.ended_at.isoformat() if meeting.ended_at else None,
        "created_at": meeting.created_at.isoformat() if meeting.created_at else None,
    }

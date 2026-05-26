import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.task import Task
from src.models.organization import Agent
from src.models.escalation import EscalationEvent
from src.repositories.task_repo import TaskRepository
from src.repositories.agent_repo import AgentRepository
from src.services.task_manager import TaskManagerService, TaskStatus
from src.core.config import settings
from src.core.exceptions import TaskNotFoundError, AgentNotFoundError, EscalationLimitExceededError


class EscalationReason(StrEnum):
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"
    NEEDS_CLARIFICATION = "needs_clarification"
    TIMEOUT = "timeout"
    CRITICAL_FAILURE = "critical_failure"
    BLOCKED_DEPENDENCY = "blocked_dependency"


class EscalationResolution(StrEnum):
    PENDING = "pending"
    MODIFY_AND_RETRY = "modify_and_retry"
    ESCALATE_HIGHER = "escalate_higher"
    RESOLVE_DIRECTLY = "resolve_directly"
    RETURN_TO_ORIGINATOR = "return_to_originator"
    CANCELLED = "cancelled"


@dataclass
class FailureAnalysis:
    task_id: uuid.UUID
    task_code: str
    reason: EscalationReason
    error_detail: str
    retry_count: int
    max_retries: int
    assigned_agent_id: uuid.UUID | None
    assigned_agent_name: str
    suggested_remedy: str = ""
    root_cause: str = ""


class EscalationEngine:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.task_repo = TaskRepository(session)
        self.agent_repo = AgentRepository(session)
        self.task_svc = TaskManagerService(session)

    async def analyze_failure(self, task_id: uuid.UUID) -> FailureAnalysis | None:
        """Analyze why a task failed and whether escalation is needed"""
        task = await self.task_repo.get(task_id)
        if not task:
            return None

        if task.status not in (TaskStatus.FAILED.value, TaskStatus.NEEDS_CLARIFICATION.value):
            return None

        # Determine escalation reason
        reason = EscalationReason.CRITICAL_FAILURE
        if task.retry_count >= task.max_retries and task.status == TaskStatus.FAILED.value:
            reason = EscalationReason.MAX_RETRIES_EXCEEDED
        elif task.status == TaskStatus.NEEDS_CLARIFICATION.value:
            reason = EscalationReason.NEEDS_CLARIFICATION

        agent_name = "未分配"
        if task.assigned_agent_id:
            agent = await self.agent_repo.get(task.assigned_agent_id)
            agent_name = agent.name if agent else "未知"

        return FailureAnalysis(
            task_id=task.id,
            task_code=task.task_code,
            reason=reason,
            error_detail=f"任务 '{task.title}' 失败: 重试{task.retry_count}/{task.max_retries}次",
            retry_count=task.retry_count,
            max_retries=task.max_retries,
            assigned_agent_id=task.assigned_agent_id,
            assigned_agent_name=agent_name,
        )

    async def escalate(self, task_id: uuid.UUID, reason: EscalationReason, triggered_by_agent_id: uuid.UUID | None = None) -> EscalationEvent:
        """Create escalation and route up the chain"""
        task = await self.task_repo.get(task_id)
        if not task:
            raise TaskNotFoundError(f"任务不存在: {task_id}")

        if task.escalation_level >= settings.task_max_escalation_depth:
            raise EscalationLimitExceededError(
                f"任务 {task.task_code} 已达最大升级深度 ({settings.task_max_escalation_depth})，请人工介入"
            )

        # Check cooldown
        recent = await self._get_recent_escalation(task_id)
        if recent:
            elapsed = (datetime.now(timezone.utc) - recent.created_at).total_seconds() / 60
            if elapsed < settings.task_escalation_cooldown_minutes:
                return recent  # Still in cooldown

        from_agent_id = task.assigned_agent_id or triggered_by_agent_id
        from_dept_id = task.assigned_department_id

        # Find the superior agent via reports_to chain
        to_agent_id = None
        to_dept_id = None
        if from_agent_id:
            agent = await self.agent_repo.get(from_agent_id)
            if agent and agent.reports_to_agent_id:
                to_agent_id = agent.reports_to_agent_id
                superior = await self.agent_repo.get(to_agent_id)
                if superior:
                    to_dept_id = superior.department_id

        # Fallback: escalate to the department head
        if not to_agent_id and from_dept_id:
            dept_agents = await self.agent_repo.list_by_department(from_dept_id)
            for a in dept_agents:
                if a.reports_to_agent_id is None and a.is_active:
                    to_agent_id = a.id
                    to_dept_id = a.department_id
                    break

        # Ultimate fallback
        if not to_agent_id:
            raise EscalationLimitExceededError(f"任务 {task.task_code} 无上级可升级，请人工介入")

        new_level = task.escalation_level + 1
        task.escalation_level = new_level

        event = EscalationEvent(
            task_id=task_id,
            from_agent_id=from_agent_id or triggered_by_agent_id or uuid.uuid4(),
            from_department_id=from_dept_id or uuid.uuid4(),
            to_agent_id=to_agent_id,
            to_department_id=to_dept_id or uuid.uuid4(),
            escalation_level=new_level,
            reason=reason.value,
            task_context={
                "task_code": task.task_code,
                "title": task.title,
                "status": task.status,
                "retry_count": task.retry_count,
                "assigned_agent": str(task.assigned_agent_id),
            },
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def resolve_escalation(self, escalation_id: uuid.UUID, resolution: EscalationResolution, resolved_by_agent_id: uuid.UUID, notes: str = "") -> EscalationEvent:
        """Superior agent resolves an escalation"""
        event = await self.session.get(EscalationEvent, escalation_id)
        if not event:
            raise TaskNotFoundError(f"升级事件不存在: {escalation_id}")

        task = await self.task_repo.get(event.task_id)
        if not task:
            raise TaskNotFoundError(f"关联任务不存在: {event.task_id}")

        event.resolution = resolution.value
        event.resolved_by_agent_id = resolved_by_agent_id
        event.resolution_notes = notes
        event.resolved_at = datetime.now(timezone.utc)

        # Apply resolution
        match resolution:
            case EscalationResolution.MODIFY_AND_RETRY:
                task.retry_count = 0
                await self.task_svc.transition_status(task.id, TaskStatus.PENDING, f"agent:{resolved_by_agent_id}")

            case EscalationResolution.ESCALATE_HIGHER:
                await self.escalate(task.id, EscalationReason.CRITICAL_FAILURE, resolved_by_agent_id)

            case EscalationResolution.RESOLVE_DIRECTLY:
                await self.task_svc.transition_status(task.id, TaskStatus.IN_PROGRESS, f"agent:{resolved_by_agent_id}")

            case EscalationResolution.RETURN_TO_ORIGINATOR:
                await self.task_svc.transition_status(task.id, TaskStatus.PENDING, f"agent:{resolved_by_agent_id}")

            case EscalationResolution.CANCELLED:
                await self.task_svc.cancel_task(task.id, f"agent:{resolved_by_agent_id}")

        await self.session.flush()
        return event

    async def get_escalations(self, task_id: uuid.UUID | None = None, agent_id: uuid.UUID | None = None) -> list[EscalationEvent]:
        from sqlalchemy import select
        stmt = select(EscalationEvent).order_by(EscalationEvent.created_at.desc()).limit(100)
        if task_id:
            stmt = stmt.where(EscalationEvent.task_id == task_id)
        if agent_id:
            stmt = stmt.where(
                (EscalationEvent.to_agent_id == agent_id) | (EscalationEvent.from_agent_id == agent_id)
            )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_escalations(self, agent_id: uuid.UUID | None = None) -> list[EscalationEvent]:
        from sqlalchemy import select
        stmt = select(EscalationEvent).where(
            EscalationEvent.resolution == EscalationResolution.PENDING.value
        ).order_by(EscalationEvent.created_at.desc())
        if agent_id:
            stmt = stmt.where(EscalationEvent.to_agent_id == agent_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_recent_escalation(self, task_id: uuid.UUID) -> EscalationEvent | None:
        from sqlalchemy import select, desc
        result = await self.session.execute(
            select(EscalationEvent)
            .where(EscalationEvent.task_id == task_id)
            .order_by(desc(EscalationEvent.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

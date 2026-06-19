"""Agent-facing APIs: heartbeat (+ atomic task claim), status report, result report.

Plus the read-only agent list for the web UI.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..enums import AgentEventType, AnalysisStatus, TaskStatus
from ..logging_config import log_event
from ..models import Agent, AgentEvent, Task
from ..schemas import (
    AgentEventOut,
    AgentOut,
    HeartbeatRequest,
    HeartbeatResponse,
    ResultReport,
    StatusReport,
    TaskDispatch,
)
from ..state import InvalidTransition, transition
from ..util import utcnow

router = APIRouter(prefix="/api/v1", tags=["agents"])
logger = logging.getLogger("minidrop.agents")


@router.get("/agents", response_model=list[AgentOut])
def list_agents(session: Session = Depends(get_session)):
    return session.execute(select(Agent).order_by(Agent.created_at)).scalars().all()


@router.get("/agents/{agent_id}/events", response_model=list[AgentEventOut])
def agent_events(agent_id: str, limit: int = 50, session: Session = Depends(get_session)):
    """The agent's lifecycle audit trail (register / offline / recover), newest first."""
    return session.execute(
        select(AgentEvent)
        .where(AgentEvent.agent_id == agent_id)
        .order_by(AgentEvent.created_at.desc())
        .limit(limit)
    ).scalars().all()


def _claim_task(session: Session, agent_id: str) -> Task | None:
    """Atomically claim one PENDING task for this agent (FOR UPDATE SKIP LOCKED).

    The claim itself performs the PENDING -> RUNNING transition so a task is never
    handed to two agents.
    """
    stmt = (
        select(Task)
        .where(
            Task.status == TaskStatus.PENDING.value,
            Task.deleted.is_(False),
            (Task.agent_id == agent_id) | (Task.agent_id.is_(None)),
        )
        .order_by(Task.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    task = session.execute(stmt).scalars().first()
    if task is None:
        return None
    task.agent_id = agent_id
    transition(session, task, TaskStatus.RUNNING.value, f"dispatched to agent {agent_id}")
    return task


@router.post("/agent/heartbeat", response_model=HeartbeatResponse)
def heartbeat(req: HeartbeatRequest, session: Session = Depends(get_session)):
    now = utcnow()
    agent = session.get(Agent, req.agent_id)
    was_offline = False
    if agent is None:
        agent = Agent(id=req.agent_id, created_at=now)
        session.add(agent)
        session.add(AgentEvent(agent_id=req.agent_id, event_type=AgentEventType.REGISTER.value,
                               detail=f"first contact from {req.hostname}/{req.ip_addr}"))
        log_event(logger, "agent registered", agent_id=req.agent_id, hostname=req.hostname)
    else:
        was_offline = not agent.online

    agent.hostname = req.hostname
    agent.ip_addr = req.ip_addr
    agent.agent_version = req.agent_version
    agent.self_stats = req.self_stats
    agent.online = True
    agent.last_heartbeat = now

    if was_offline:
        session.add(AgentEvent(agent_id=req.agent_id, event_type=AgentEventType.RECOVER.value,
                               detail="heartbeat resumed after being marked offline"))
        log_event(logger, "agent recovered", agent_id=req.agent_id)

    claimed = _claim_task(session, req.agent_id)
    session.commit()

    dispatch = None
    if claimed is not None:
        dispatch = TaskDispatch(
            tid=claimed.tid,
            target_pid=claimed.target_pid,
            duration_sec=claimed.duration_sec,
            frequency_hz=claimed.frequency_hz,
            profiler_type=claimed.profiler_type,
        )
        log_event(logger, "task dispatched", tid=claimed.tid, agent_id=req.agent_id)

    return HeartbeatResponse(
        online=True, heartbeat_interval_sec=settings.heartbeat_interval_sec, task=dispatch
    )


def _get_task_or_404(session: Session, tid: str) -> Task:
    task = session.get(Task, tid)
    if task is None or task.deleted:
        raise HTTPException(status_code=404, detail=f"task {tid} not found")
    return task


@router.post("/agent/tasks/{tid}/status", response_model=dict)
def report_status(tid: str, req: StatusReport, session: Session = Depends(get_session)):
    task = _get_task_or_404(session, tid)
    try:
        transition(session, task, req.status, req.reason or f"agent reported {req.status}")
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    session.commit()
    return {"tid": tid, "status": task.status}


@router.post("/agent/tasks/{tid}/result", response_model=dict)
def report_result(tid: str, req: ResultReport, session: Session = Depends(get_session)):
    task = _get_task_or_404(session, tid)
    try:
        if req.success:
            # Agent may post the result directly from RUNNING; normalize through UPLOADING.
            if task.status == TaskStatus.RUNNING.value:
                transition(session, task, TaskStatus.UPLOADING.value, "result received from agent")
            task.result_files = req.result_files or {}
            transition(session, task, TaskStatus.DONE.value, "collection artifact stored")
            task.analysis_status = AnalysisStatus.PENDING.value
            task.analysis_reason = "queued for analysis"
        else:
            task.error_message = req.error_message
            transition(session, task, TaskStatus.FAILED.value,
                       req.error_message or "collection failed on agent")
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    session.commit()
    log_event(logger, "task result", tid=tid, success=req.success, status=task.status)
    return {"tid": tid, "status": task.status}

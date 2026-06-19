"""Background offline detector.

Runs as an asyncio task for the lifetime of the server. Every monitor_interval_sec it:
  - marks agents offline when their last heartbeat is older than offline_threshold_sec,
    writing an OFFLINE audit event;
  - fails any task that was still RUNNING/UPLOADING on a now-offline agent, so a
    crashed/disconnected agent never leaves a task stuck forever.

DB work is synchronous SQLAlchemy, so it is wrapped in asyncio.to_thread to avoid
blocking the event loop.
"""
import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from .config import settings
from .db import SessionLocal
from .enums import AgentEventType, TaskStatus
from .logging_config import log_event
from .models import Agent, AgentEvent, Task
from .state import transition
from .util import utcnow

logger = logging.getLogger("minidrop.monitor")


def _scan_once() -> None:
    threshold = utcnow() - timedelta(seconds=settings.offline_threshold_sec)
    with SessionLocal() as session:
        stale = session.execute(
            select(Agent).where(Agent.online.is_(True), Agent.last_heartbeat < threshold)
        ).scalars().all()
        for agent in stale:
            agent.online = False
            session.add(AgentEvent(
                agent_id=agent.id,
                event_type=AgentEventType.OFFLINE.value,
                detail=f"no heartbeat for >{settings.offline_threshold_sec}s "
                       f"(last={agent.last_heartbeat.isoformat() if agent.last_heartbeat else 'never'})",
            ))
            log_event(logger, "agent offline", agent_id=agent.id)

            running = session.execute(
                select(Task).where(
                    Task.agent_id == agent.id,
                    Task.status.in_([TaskStatus.RUNNING.value, TaskStatus.UPLOADING.value]),
                    Task.deleted.is_(False),
                )
            ).scalars().all()
            for task in running:
                transition(session, task, TaskStatus.FAILED.value,
                           f"agent {agent.id} went offline during collection")
                log_event(logger, "task failed: agent offline", tid=task.tid, agent_id=agent.id)
        session.commit()


async def offline_monitor() -> None:
    log_event(logger, "offline monitor started",
              interval=settings.monitor_interval_sec, threshold=settings.offline_threshold_sec)
    while True:
        await asyncio.sleep(settings.monitor_interval_sec)
        try:
            await asyncio.to_thread(_scan_once)
        except Exception:  # never let the monitor die on a transient DB hiccup
            logger.exception("offline monitor scan failed")

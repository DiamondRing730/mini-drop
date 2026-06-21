"""Task state-machine. The ONLY sanctioned way to change task.status.

Every call validates the edge against ALLOWED_TRANSITIONS, updates the task row,
and appends a TaskStateTransition audit row carrying the human-readable reason.
"""
import logging

from sqlalchemy.orm import Session

from .enums import ALLOWED_TRANSITIONS, TaskStatus
from .logging_config import log_event
from .models import Task, TaskStateTransition
from .util import utcnow

logger = logging.getLogger("minidrop.state")


class InvalidTransition(Exception):
    """Raised when a state change is not permitted by the state machine."""


def record_initial(session: Session, task: Task, reason: str) -> None:
    """Record the synthetic None -> PENDING edge at task creation time."""
    session.add(
        TaskStateTransition(
            tid=task.tid, from_status=None, to_status=task.status, reason=reason, created_at=utcnow()
        )
    )
    log_event(logger, "task created", tid=task.tid, to=task.status, reason=reason)


def transition(session: Session, task: Task, to_status: str, reason: str) -> None:
    """Move `task` to `to_status`, persisting the change and a reasoned audit row.

    Raises InvalidTransition if the edge is illegal. Caller owns the commit.
    """
    frm = TaskStatus(task.status)
    to = TaskStatus(to_status)
    if to not in ALLOWED_TRANSITIONS[frm]:
        raise InvalidTransition(f"illegal transition {frm.value} -> {to.value} (tid={task.tid})")

    now = utcnow()
    task.status = to.value
    task.status_reason = reason
    if to == TaskStatus.RUNNING and task.begin_time is None:
        task.begin_time = now
    if to in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.STOPPED):
        task.end_time = now

    session.add(
        TaskStateTransition(
            tid=task.tid, from_status=frm.value, to_status=to.value, reason=reason, created_at=now
        )
    )
    log_event(logger, "task transition", tid=task.tid, **{"from": frm.value, "to": to.value, "reason": reason})

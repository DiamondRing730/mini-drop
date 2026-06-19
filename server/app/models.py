"""SQLAlchemy ORM models. Tables are auto-created on startup (create_all)."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .enums import AnalysisStatus, TaskStatus
from .util import utcnow


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hostname: Mapped[str] = mapped_column(String(255), default="")
    ip_addr: Mapped[str] = mapped_column(String(64), default="")
    agent_version: Mapped[str] = mapped_column(String(32), default="")
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Latest self-resource snapshot reported on heartbeat (cpu_pct / rss_kb / io_kbps ...).
    self_stats: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Task(Base):
    __tablename__ = "tasks"

    tid: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    target_pid: Mapped[int] = mapped_column(Integer)
    duration_sec: Mapped[int] = mapped_column(Integer, default=10)
    frequency_hz: Mapped[int] = mapped_column(Integer, default=99)
    profiler_type: Mapped[str] = mapped_column(String(16))

    agent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[str] = mapped_column(String(16), default=TaskStatus.PENDING.value, index=True)
    status_reason: Mapped[str] = mapped_column(Text, default="")
    analysis_status: Mapped[str] = mapped_column(String(16), default=AnalysisStatus.NONE.value, index=True)
    analysis_reason: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str] = mapped_column(Text, default="")

    # logical-name -> filename, all under <artifacts_dir>/<tid>/
    result_files: Mapped[dict] = mapped_column(JSON, default=dict)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    begin_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    transitions: Mapped[list["TaskStateTransition"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskStateTransition.id"
    )


class TaskStateTransition(Base):
    """One row per state change — the durable, reasoned audit trail of the state machine."""
    __tablename__ = "task_state_transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tid: Mapped[str] = mapped_column(ForeignKey("tasks.tid"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    task: Mapped["Task"] = relationship(back_populates="transitions")


class AgentEvent(Base):
    """Audit log of agent lifecycle: register / offline / recover."""
    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(16))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

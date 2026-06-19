"""Pydantic request/response models (the wire contract)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import ProfilerType

# ---------- frontend: create / view tasks ----------


class CreateTaskRequest(BaseModel):
    name: str = Field(default="", max_length=255)
    target_pid: int = Field(gt=0)
    duration_sec: int = Field(default=10, ge=1, le=600)
    frequency_hz: int = Field(default=99, ge=1, le=999)
    profiler_type: ProfilerType = ProfilerType.PERF
    agent_id: str | None = None  # if None, any online agent may claim it


class TransitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    from_status: str | None
    to_status: str
    reason: str
    created_at: datetime


class TaskSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tid: str
    name: str
    target_pid: int
    profiler_type: str
    status: str
    status_reason: str
    analysis_status: str
    agent_id: str | None
    created_at: datetime


class TaskDetail(TaskSummary):
    duration_sec: int
    frequency_hz: int
    analysis_reason: str
    error_message: str
    result_files: dict
    begin_time: datetime | None
    end_time: datetime | None
    transitions: list[TransitionOut]


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    hostname: str
    ip_addr: str
    agent_version: str
    online: bool
    last_heartbeat: datetime | None
    self_stats: dict


class AgentEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    event_type: str
    detail: str
    created_at: datetime


# ---------- agent: heartbeat / status / result ----------


class HeartbeatRequest(BaseModel):
    agent_id: str
    hostname: str = ""
    ip_addr: str = ""
    agent_version: str = ""
    self_stats: dict = Field(default_factory=dict)


class TaskDispatch(BaseModel):
    tid: str
    target_pid: int
    duration_sec: int
    frequency_hz: int
    profiler_type: str


class HeartbeatResponse(BaseModel):
    online: bool = True
    heartbeat_interval_sec: int
    task: TaskDispatch | None = None


class StatusReport(BaseModel):
    status: str
    reason: str = ""


class ResultReport(BaseModel):
    success: bool
    error_message: str = ""
    result_files: dict = Field(default_factory=dict)


# ---------- analyzer: claim / report ----------


class AnalysisJob(BaseModel):
    tid: str
    profiler_type: str
    result_files: dict


class AnalysisNextResponse(BaseModel):
    task: AnalysisJob | None = None


class AnalysisResultReport(BaseModel):
    success: bool
    analysis_files: dict = Field(default_factory=dict)
    error: str = ""

"""Pydantic request/response models (the wire contract)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import ProfilerType, TaskMode

# ---------- frontend: create / view tasks ----------


class CreateTaskRequest(BaseModel):
    name: str = Field(default="", max_length=255)
    # 0 is allowed and means "system-wide" for the eBPF collector; perf/py-spy reject it.
    target_pid: int = Field(ge=0)
    duration_sec: int = Field(default=10, ge=1, le=3600)  # also = session length when continuous
    frequency_hz: int = Field(default=99, ge=1, le=999)
    profiler_type: ProfilerType = ProfilerType.PERF
    mode: TaskMode = TaskMode.ONESHOT
    slice_sec: int = Field(default=10, ge=1, le=60)  # per-capture length when continuous
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
    mode: str
    status: str
    status_reason: str
    analysis_status: str
    agent_id: str | None
    stop_requested: bool
    created_at: datetime


class TaskDetail(TaskSummary):
    duration_sec: int
    frequency_hz: int
    slice_sec: int
    analysis_reason: str
    error_message: str
    result_files: dict
    begin_time: datetime | None
    end_time: datetime | None
    transitions: list[TransitionOut]


class TaskListResponse(BaseModel):
    items: list[TaskSummary]
    total: int
    page: int
    page_size: int


class ArtifactOut(BaseModel):
    path: str
    logical_name: str | None = None
    size_bytes: int
    content_type: str


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    hostname: str
    ip_addr: str
    agent_version: str
    online: bool
    last_heartbeat: datetime | None
    self_stats: dict
    discovery: list[dict] = Field(default_factory=list)


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
    discovery: list[dict] = Field(default_factory=list)
    # Tasks currently queued or executing in this Agent process. An empty list after
    # a restart lets the server safely redispatch previously claimed RUNNING tasks.
    active_task_ids: list[str] = Field(default_factory=list)


class TaskDispatch(BaseModel):
    tid: str
    target_pid: int
    duration_sec: int
    frequency_hz: int
    profiler_type: str
    mode: str
    slice_sec: int


class HeartbeatResponse(BaseModel):
    online: bool = True
    heartbeat_interval_sec: int
    task: TaskDispatch | None = None
    stop_task_ids: list[str] = Field(default_factory=list)


class StatusReport(BaseModel):
    status: str
    reason: str = ""


class ChunkReport(BaseModel):
    start_ts: float
    end_ts: float
    folded_file: str
    samples: int = 0


class TimelineEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    start_ts: float
    end_ts: float
    samples: int


class ResultReport(BaseModel):
    success: bool
    stopped: bool = False
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

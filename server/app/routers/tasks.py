"""Frontend-facing task APIs: create / list / detail / soft-delete / artifact download."""
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import flame
from ..config import settings
from ..db import get_session
from ..enums import TaskStatus
from ..logging_config import log_event
from ..models import ProfileChunk, Task
from ..schemas import CreateTaskRequest, TaskDetail, TaskSummary, TimelineEntry
from ..state import record_initial
from ..util import short_id, utcnow

router = APIRouter(prefix="/api/v1", tags=["tasks"])
logger = logging.getLogger("minidrop.tasks")


@router.post("/tasks", response_model=dict)
def create_task(req: CreateTaskRequest, session: Session = Depends(get_session)):
    tid = short_id()
    task = Task(
        tid=tid,
        name=req.name or f"{req.profiler_type.value}-pid{req.target_pid}",
        target_pid=req.target_pid,
        duration_sec=req.duration_sec,
        frequency_hz=req.frequency_hz,
        profiler_type=req.profiler_type.value,
        mode=req.mode.value,
        slice_sec=req.slice_sec,
        agent_id=req.agent_id,
        status=TaskStatus.PENDING.value,
        status_reason="task created by user",
        created_at=utcnow(),
    )
    session.add(task)
    session.flush()  # ensure tid exists for the FK in the transition row
    record_initial(session, task, "task created by user")
    session.commit()
    log_event(logger, "task created", tid=tid, pid=req.target_pid, profiler=req.profiler_type.value)
    return {"tid": tid}


@router.get("/tasks", response_model=list[TaskSummary])
def list_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    rows = session.execute(
        select(Task)
        .where(Task.deleted.is_(False))
        .order_by(Task.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return rows


def _get_task_or_404(session: Session, tid: str) -> Task:
    task = session.get(Task, tid)
    if task is None or task.deleted:
        raise HTTPException(status_code=404, detail=f"task {tid} not found")
    return task


@router.get("/tasks/{tid}", response_model=TaskDetail)
def get_task(tid: str, session: Session = Depends(get_session)):
    return _get_task_or_404(session, tid)


@router.delete("/tasks/{tid}", response_model=dict)
def delete_task(tid: str, session: Session = Depends(get_session)):
    task = _get_task_or_404(session, tid)
    task.deleted = True
    session.commit()
    log_event(logger, "task soft-deleted", tid=tid)
    return {"deleted": tid}


@router.get("/tasks/{tid}/artifacts/{filename}")
def get_artifact(tid: str, filename: str, session: Session = Depends(get_session)):
    _get_task_or_404(session, tid)
    # basename guard: never let a crafted filename escape the task's artifact dir.
    safe = os.path.basename(filename)
    path = os.path.join(settings.artifacts_dir, tid, safe)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"artifact {safe} not found")
    media = "image/svg+xml" if safe.endswith(".svg") else None
    # Flamegraphs are rendered inside the Web UI's iframe.  Any Content-Disposition
    # header can make browsers treat the SVG as a download, so omit it entirely for SVGs.
    # Other artifacts retain explicit attachment/download semantics.
    if safe.endswith(".svg"):
        return FileResponse(path, media_type=media)
    return FileResponse(path, media_type=media, filename=safe)


# ---- continuous profiling: timeline + on-demand window flamegraph ----


@router.get("/tasks/{tid}/timeline", response_model=list[TimelineEntry])
def timeline(tid: str, session: Session = Depends(get_session)):
    """All captured slices of a continuous session, ordered in time."""
    _get_task_or_404(session, tid)
    return session.execute(
        select(ProfileChunk).where(ProfileChunk.tid == tid).order_by(ProfileChunk.start_ts)
    ).scalars().all()


@router.get("/tasks/{tid}/window")
def window_flame(
    tid: str,
    from_ts: float = Query(alias="from"),
    to_ts: float = Query(alias="to"),
    session: Session = Depends(get_session),
):
    """Render a flamegraph for [from, to] by merging all chunks overlapping that window."""
    _get_task_or_404(session, tid)
    chunks = session.execute(
        select(ProfileChunk).where(
            ProfileChunk.tid == tid,
            ProfileChunk.start_ts <= to_ts,
            ProfileChunk.end_ts >= from_ts,
        ).order_by(ProfileChunk.start_ts)
    ).scalars().all()

    paths = [os.path.join(settings.artifacts_dir, tid, "chunks", c.folded_file) for c in chunks]
    folded = flame.merge_folded_files(paths)
    if folded:
        tree = flame.build_tree(folded, root_name="window")
        title = f"window {int(from_ts)}–{int(to_ts)} ({len(chunks)} slices, {tree['value']} samples)"
    else:
        tree = {"name": "no data in window", "value": 0, "children": []}
        title = "no data in selected window"
    svg = flame.render_svg(tree, title=title)
    return Response(content=svg, media_type="image/svg+xml")

"""Frontend-facing task APIs: create / list / detail / soft-delete / artifact download."""
import logging
import mimetypes
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import flame
from ..config import settings
from ..db import get_session
from ..enums import AnalysisStatus, TaskMode, TaskStatus
from ..logging_config import log_event
from ..models import ProfileChunk, Task
from ..schemas import (
    ArtifactOut,
    CreateTaskRequest,
    TaskDetail,
    TaskListResponse,
    TimelineEntry,
)
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


@router.get("/tasks", response_model=TaskListResponse)
def list_tasks(
    q: str = Query(default="", max_length=255),
    status: str | None = Query(default=None),
    profiler_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    session: Session = Depends(get_session),
):
    filters = [Task.deleted.is_(False)]
    query_text = q.strip()
    if query_text:
        search_terms = [
            Task.name.ilike(f"%{query_text}%"),
            Task.tid.ilike(f"%{query_text}%"),
        ]
        if query_text.isdigit():
            search_terms.append(Task.target_pid == int(query_text))
        filters.append(or_(*search_terms))
    if status:
        filters.append(Task.status == status)
    if profiler_type:
        filters.append(Task.profiler_type == profiler_type)

    total = session.scalar(select(func.count()).select_from(Task).where(*filters)) or 0
    rows = session.execute(
        select(Task).where(*filters)
        .order_by(Task.created_at.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).scalars().all()
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


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


@router.post("/tasks/{tid}/retry", response_model=dict)
def retry_task(tid: str, session: Session = Depends(get_session)):
    source = _get_task_or_404(session, tid)
    if source.status not in {TaskStatus.DONE.value, TaskStatus.FAILED.value}:
        raise HTTPException(status_code=409, detail="only finished or failed tasks can be retried")

    new_tid = short_id()
    reason = f"retried from task {source.tid}"
    task = Task(
        tid=new_tid,
        name=source.name,
        target_pid=source.target_pid,
        duration_sec=source.duration_sec,
        frequency_hz=source.frequency_hz,
        profiler_type=source.profiler_type,
        mode=source.mode,
        slice_sec=source.slice_sec,
        agent_id=source.agent_id,
        status=TaskStatus.PENDING.value,
        status_reason=reason,
        created_at=utcnow(),
    )
    session.add(task)
    session.flush()
    record_initial(session, task, reason)
    session.commit()
    log_event(logger, "task retried", tid=new_tid, source_tid=source.tid)
    return {"tid": new_tid, "source_tid": source.tid}


@router.post("/tasks/{tid}/stop", response_model=dict)
def stop_task(tid: str, session: Session = Depends(get_session)):
    """Request a continuous session to stop at the next slice boundary."""
    task = _get_task_or_404(session, tid)
    if task.mode != TaskMode.CONTINUOUS.value:
        raise HTTPException(status_code=400, detail="only continuous tasks can be stopped")
    if task.status == TaskStatus.PENDING.value:
        from ..state import transition
        transition(session, task, TaskStatus.STOPPED.value, "stopped by user before dispatch")
        task.analysis_status = AnalysisStatus.DONE.value
        task.analysis_reason = "stopped before any profiling slice was captured"
    elif task.status == TaskStatus.RUNNING.value:
        task.stop_requested = True
        task.status_reason = "stop requested by user; waiting for current slice"
    else:
        raise HTTPException(status_code=409, detail=f"task in {task.status} cannot be stopped")
    session.commit()
    log_event(logger, "continuous stop requested", tid=tid, status=task.status)
    return {"tid": tid, "status": task.status, "stop_requested": task.stop_requested}


@router.post("/tasks/{tid}/resume", response_model=dict)
def resume_task(tid: str, session: Session = Depends(get_session)):
    """Continue a stopped session as a new task, preserving the old timeline."""
    source = _get_task_or_404(session, tid)
    if source.mode != TaskMode.CONTINUOUS.value:
        raise HTTPException(status_code=400, detail="only continuous tasks can be resumed")
    if source.status != TaskStatus.STOPPED.value:
        raise HTTPException(status_code=409, detail="only stopped continuous tasks can be resumed")

    new_tid = short_id()
    reason = f"resumed from task {source.tid}"
    task = Task(
        tid=new_tid, name=source.name, target_pid=source.target_pid,
        duration_sec=source.duration_sec, frequency_hz=source.frequency_hz,
        profiler_type=source.profiler_type, mode=source.mode, slice_sec=source.slice_sec,
        agent_id=source.agent_id, status=TaskStatus.PENDING.value,
        status_reason=reason, created_at=utcnow(),
    )
    session.add(task)
    session.flush()
    record_initial(session, task, reason)
    session.commit()
    log_event(logger, "continuous task resumed", tid=new_tid, source_tid=source.tid)
    return {"tid": new_tid, "source_tid": source.tid}


def _artifact_root(tid: str) -> Path:
    return (Path(settings.artifacts_dir) / tid).resolve()


@router.get("/tasks/{tid}/artifacts", response_model=list[ArtifactOut])
def list_artifacts(tid: str, session: Session = Depends(get_session)):
    task = _get_task_or_404(session, tid)
    root = _artifact_root(tid)
    if not root.is_dir():
        return []

    logical_by_path = {
        str(filename).replace("\\", "/"): logical
        for logical, filename in (task.result_files or {}).items()
        if isinstance(filename, str)
    }
    artifacts = []
    for candidate in root.rglob("*"):
        resolved = candidate.resolve()
        if not resolved.is_file() or not resolved.is_relative_to(root):
            continue
        relative = resolved.relative_to(root).as_posix()
        content_type = mimetypes.guess_type(relative)[0] or "application/octet-stream"
        artifacts.append({
            "path": relative,
            "logical_name": logical_by_path.get(relative),
            "size_bytes": resolved.stat().st_size,
            "content_type": content_type,
        })
    return sorted(artifacts, key=lambda item: item["path"])


@router.get("/tasks/{tid}/artifacts/{file_path:path}")
def get_artifact(
    tid: str,
    file_path: str,
    download: bool = Query(default=False),
    session: Session = Depends(get_session),
):
    _get_task_or_404(session, tid)
    root = _artifact_root(tid)
    path = (root / file_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail=f"artifact {file_path} not found")
    media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    # Flamegraphs are rendered inside the Web UI's iframe.  Any Content-Disposition
    # header can make browsers treat the SVG as a download, so omit it entirely for SVGs.
    # Other artifacts retain explicit attachment/download semantics.
    if path.suffix.lower() == ".svg" and not download:
        return FileResponse(path, media_type=media)
    return FileResponse(path, media_type=media, filename=path.name)


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

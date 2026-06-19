"""Internal analyzer APIs: claim the next analyzable task, report analysis result."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..enums import AnalysisStatus, TaskStatus
from ..logging_config import log_event
from ..models import Task
from ..schemas import AnalysisJob, AnalysisNextResponse, AnalysisResultReport

router = APIRouter(prefix="/api/v1/internal/analysis", tags=["analysis"])
logger = logging.getLogger("minidrop.analysis")


@router.get("/next", response_model=AnalysisNextResponse)
def next_analysis(session: Session = Depends(get_session)):
    """Atomically claim one finished-but-unanalyzed task."""
    stmt = (
        select(Task)
        .where(
            Task.status == TaskStatus.DONE.value,
            Task.analysis_status == AnalysisStatus.PENDING.value,
            Task.deleted.is_(False),
        )
        .order_by(Task.end_time)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    task = session.execute(stmt).scalars().first()
    if task is None:
        return AnalysisNextResponse(task=None)
    task.analysis_status = AnalysisStatus.RUNNING.value
    task.analysis_reason = "analyzer processing"
    session.commit()
    log_event(logger, "analysis claimed", tid=task.tid)
    return AnalysisNextResponse(
        task=AnalysisJob(tid=task.tid, profiler_type=task.profiler_type, result_files=task.result_files or {})
    )


@router.post("/{tid}/result", response_model=dict)
def analysis_result(tid: str, req: AnalysisResultReport, session: Session = Depends(get_session)):
    task = session.get(Task, tid)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task {tid} not found")
    if req.success:
        merged = dict(task.result_files or {})
        merged.update(req.analysis_files or {})
        task.result_files = merged
        task.analysis_status = AnalysisStatus.DONE.value
        task.analysis_reason = "analysis complete"
    else:
        task.analysis_status = AnalysisStatus.FAILED.value
        task.analysis_reason = req.error or "analysis failed"
    session.commit()
    log_event(logger, "analysis result", tid=tid, success=req.success)
    return {"tid": tid, "analysis_status": task.analysis_status}

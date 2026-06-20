"""Verified before/after profile comparison API."""
import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..attribution.profile import load_profile
from ..comparison import compare_profiles, render_diff_flamegraph, verify_comparison
from ..config import settings
from ..db import get_session
from ..enums import AnalysisStatus, TaskStatus
from ..logging_config import log_event
from ..models import Task

router = APIRouter(prefix="/api/v1", tags=["comparison"])
logger = logging.getLogger("minidrop.comparison")


class ComparisonRequest(BaseModel):
    baseline_tid: str


def _task(session: Session, tid: str) -> Task:
    task = session.get(Task, tid)
    if task is None or task.deleted:
        raise HTTPException(status_code=404, detail=f"task {tid} not found")
    return task


def _profile(task: Task):
    files = task.result_files or {}
    if task.status != TaskStatus.DONE.value or task.analysis_status != AnalysisStatus.DONE.value:
        raise HTTPException(status_code=409, detail=f"task {task.tid} is not fully analyzed")
    if "tree" not in files and "topn" not in files:
        raise HTTPException(status_code=400, detail=f"task {task.tid} has no comparable flamegraph profile")
    return load_profile(settings.artifacts_dir, task.tid, task.profiler_type, files)


@router.post("/tasks/{candidate_tid}/comparison", response_model=dict)
def compare_tasks(
    candidate_tid: str,
    req: ComparisonRequest,
    session: Session = Depends(get_session),
):
    if candidate_tid == req.baseline_tid:
        raise HTTPException(status_code=400, detail="baseline and candidate must be different tasks")
    baseline_task = _task(session, req.baseline_tid)
    candidate_task = _task(session, candidate_tid)
    if baseline_task.profiler_type != candidate_task.profiler_type:
        raise HTTPException(status_code=400, detail="tasks must use the same profiler type")

    baseline = _profile(baseline_task)
    candidate = _profile(candidate_task)
    report = compare_profiles(baseline, candidate)
    report["verification"] = verify_comparison(baseline, candidate, report["functions"])
    report["baseline"] = {
        "tid": baseline_task.tid, "name": baseline_task.name,
        "profiler_type": baseline_task.profiler_type, "total_samples": baseline.total_samples,
    }
    report["candidate"] = {
        "tid": candidate_task.tid, "name": candidate_task.name,
        "profiler_type": candidate_task.profiler_type, "total_samples": candidate.total_samples,
    }

    safe_baseline = "".join(ch for ch in baseline_task.tid if ch.isalnum() or ch in "-_")
    report_name = f"comparison-{safe_baseline}.json"
    flame_name = f"diff-flamegraph-{safe_baseline}.svg"
    report["artifacts"] = {"report": report_name, "diff_flamegraph": flame_name}
    out_dir = os.path.join(settings.artifacts_dir, candidate_task.tid)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, report_name), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    svg = render_diff_flamegraph(
        baseline, candidate,
        title=f"Diff: {baseline_task.name or baseline_task.tid} -> {candidate_task.name or candidate_task.tid}",
    )
    with open(os.path.join(out_dir, flame_name), "w", encoding="utf-8") as f:
        f.write(svg)

    merged = dict(candidate_task.result_files or {})
    merged[f"comparison_{safe_baseline}"] = report_name
    merged[f"diff_flamegraph_{safe_baseline}"] = flame_name
    candidate_task.result_files = merged
    session.commit()
    log_event(
        logger, "profile comparison done", baseline_tid=baseline_task.tid,
        candidate_tid=candidate_task.tid, verdict=report["verdict"],
        verified=report["verification"]["verified"],
    )
    return report

"""Frontend-facing AI attribution API.

POST /api/v1/tasks/{tid}/attribution
  Run the constrained tool-calling analyst over the task's analyzed profile, verify
  every finding against the raw data, persist the result as the `attribution.json`
  artifact (referenced from result_files["attribution"]), and return it.

The request explicitly selects either the deterministic offline engine or DeepSeek.
DeepSeek failures are returned to the caller and never silently fall back to offline.
"""
import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Literal

from ..attribution.engine import AttributionBackendError, attribute
from ..attribution.profile import load_profile
from ..attribution.verifier import verify
from ..config import settings
from ..db import get_session
from ..enums import AnalysisStatus
from ..logging_config import log_event
from ..models import Task

router = APIRouter(prefix="/api/v1", tags=["attribution"])
logger = logging.getLogger("minidrop.attribution")


class AttributionRequest(BaseModel):
    engine: Literal["offline", "deepseek"] = "offline"


def _get_task_or_404(session: Session, tid: str) -> Task:
    task = session.get(Task, tid)
    if task is None or task.deleted:
        raise HTTPException(status_code=404, detail=f"task {tid} not found")
    return task


@router.post("/tasks/{tid}/attribution", response_model=dict)
def run_attribution(
    tid: str,
    req: AttributionRequest | None = None,
    session: Session = Depends(get_session),
):
    task = _get_task_or_404(session, tid)
    files = task.result_files or {}

    # Attribution needs the analyzer's flamegraph artifacts. eBPF tasks have no call
    # tree (they produce a latency distribution), so attribution doesn't apply there.
    if task.analysis_status != AnalysisStatus.DONE.value:
        raise HTTPException(status_code=409, detail="analysis not complete yet")
    if "tree" not in files and "topn" not in files:
        raise HTTPException(status_code=400, detail="no flamegraph profile to attribute (eBPF tasks are unsupported)")

    prof = load_profile(settings.artifacts_dir, tid, task.profiler_type, files)
    backend = req.engine if req else "offline"
    try:
        result = attribute(prof, backend=backend)
    except AttributionBackendError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    report = verify(prof, result.get("findings", []))

    payload = {
        "tid": tid,
        "engine": result.get("engine"),
        "model": result.get("model"),
        "summary": result.get("summary", ""),
        "findings": result.get("findings", []),
        "tool_trace": result.get("tool_trace", []),
        "verification": report,
    }

    # Persist as an artifact so the Web UI can reload it without re-running the LLM.
    out_dir = os.path.join(settings.artifacts_dir, tid)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "attribution.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    merged = dict(files)
    merged["attribution"] = "attribution.json"
    task.result_files = merged
    session.commit()

    log_event(
        logger, "attribution done", tid=tid, engine=payload["engine"],
        findings=len(payload["findings"]), verified=report["verified"],
    )
    return payload

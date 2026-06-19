"""Task worker: run the right collector, then report status/result back to the server."""
import logging
import os

from .client import ServerClient
from .collectors.base import Collector, CollectorError

logger = logging.getLogger("minidrop.agent.runner")


def run_task(task: dict, client: ServerClient, collectors: dict[str, Collector], artifacts_dir: str) -> None:
    tid = task["tid"]
    profiler = task["profiler_type"]
    out_dir = os.path.join(artifacts_dir, tid)
    os.makedirs(out_dir, exist_ok=True)

    collector = collectors.get(profiler)
    if collector is None:
        client.report_result(tid, False, error=f"no collector for profiler_type={profiler}")
        return

    try:
        files = collector.collect(task, out_dir)
        # The artifact already lives on the shared volume; UPLOADING marks the store step.
        client.report_status(tid, "UPLOADING", "collection finished, storing artifact")
        client.report_result(tid, True, files=files)
        logger.info("task %s collected via %s -> %s", tid, profiler, files)
    except CollectorError as exc:
        logger.warning("task %s collection failed: %s", tid, exc)
        client.report_result(tid, False, error=str(exc))
    except Exception as exc:  # defensive: never let the worker thread die silently
        logger.exception("task %s crashed in agent", tid)
        client.report_result(tid, False, error=f"agent internal error: {exc}")

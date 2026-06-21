"""Task worker: run the right collector, then report status/result back to the server."""
import logging
import os
import time
import threading

from .client import ServerClient
from .collectors.base import Collector, CollectorError

logger = logging.getLogger("minidrop.agent.runner")


def run_task(task: dict, client: ServerClient, collectors: dict[str, Collector], artifacts_dir: str,
             stop_event: threading.Event | None = None) -> None:
    if task.get("mode") == "continuous":
        run_continuous(task, client, collectors, artifacts_dir, stop_event or threading.Event())
        return

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


def run_continuous(task: dict, client: ServerClient, collectors: dict[str, Collector], artifacts_dir: str,
                   stop_event: threading.Event) -> None:
    """Resident low-frequency profiling: capture repeated slices and report each as a chunk.

    Each slice is a self-contained folded-stack file; the server merges whatever slices fall
    in a requested window to render that window's flamegraph on demand.
    """
    tid = task["tid"]
    profiler = task["profiler_type"]
    total = int(task["duration_sec"])
    slice_sec = int(task.get("slice_sec", 10))
    chunks_dir = os.path.join(artifacts_dir, tid, "chunks")
    os.makedirs(chunks_dir, exist_ok=True)

    collector = collectors.get(profiler)
    if collector is None or not hasattr(collector, "collect_slice"):
        client.report_result(
            tid, False,
            error=f"continuous mode supports py-spy targets only (got profiler_type={profiler})",
        )
        return

    deadline = time.monotonic() + total
    n = 0
    try:
        while time.monotonic() < deadline and not stop_event.is_set():
            start_ts = time.time()
            fname = f"chunk_{int(start_ts)}_{n}.folded"
            try:
                samples = collector.collect_slice(task, os.path.join(chunks_dir, fname), slice_sec)
            except CollectorError as exc:
                logger.warning("continuous %s slice %d failed: %s", tid, n, exc)
                # target may have exited; end the session rather than spin.
                if not os.path.isdir(f"/proc/{int(task['target_pid'])}"):
                    break
                continue
            end_ts = time.time()
            client.report_chunk(tid, start_ts, end_ts, fname, samples)
            logger.info("continuous %s slice %d: %d samples", tid, n, samples)
            n += 1

            if stop_event.is_set():
                break

        if stop_event.is_set():
            client.report_result(tid, False, stopped=True,
                                 files={"mode": "continuous", "chunks": str(n)})
            logger.info("continuous %s stopped after %d slices", tid, n)
            return
        client.report_status(tid, "UPLOADING", f"continuous session finished ({n} slices)")
        client.report_result(tid, True, files={"mode": "continuous", "chunks": str(n)})
    except Exception as exc:
        logger.exception("continuous %s crashed", tid)
        client.report_result(tid, False, error=f"agent internal error: {exc}")

"""Agent entrypoint.

Two cooperating loops:
  - the main thread heartbeats every ~5s and enqueues any claimed task;
  - a daemon worker thread drains the queue and runs collections.

Collection happens on the worker thread, so a long perf/py-spy run NEVER blocks the
heartbeat — which is what keeps the agent from being falsely marked offline mid-collection.
"""
import logging
import queue
import threading
import time

from .client import ServerClient
from .collectors.ebpf import EbpfCollector
from .collectors.perf import PerfCollector
from .collectors.pyspy import PySpyCollector
from .config import Config
from .discovery import DiscoveryCache
from .logging_config import configure_logging
from .pidstats import PidStatsSampler
from .runner import run_task

logger = logging.getLogger("minidrop.agent")


def _worker(task_queue: "queue.Queue[dict]", client, collectors, artifacts_dir,
            stop_events: dict[str, threading.Event], active_tasks: set[str],
            control_lock: threading.Lock) -> None:
    while True:
        task = task_queue.get()
        try:
            with control_lock:
                event = stop_events.setdefault(task["tid"], threading.Event())
            run_task(task, client, collectors, artifacts_dir, event)
        except Exception:
            # One failed report/collector must never kill the only worker thread.
            # Removing the task from active_tasks lets the next heartbeat recover it.
            logger.exception("task %s escaped the runner; worker remains alive", task.get("tid"))
        finally:
            with control_lock:
                stop_events.pop(task["tid"], None)
                active_tasks.discard(task["tid"])
            task_queue.task_done()


def main() -> None:
    configure_logging()
    cfg = Config()
    client = ServerClient(cfg.server_url)
    sampler = PidStatsSampler()
    discovery = DiscoveryCache()
    collectors = {
        "perf": PerfCollector(cfg.perf_event),
        "pyspy": PySpyCollector(),
        "ebpf": EbpfCollector(),
    }
    task_queue: "queue.Queue[dict]" = queue.Queue()
    stop_events: dict[str, threading.Event] = {}
    active_tasks: set[str] = set()
    control_lock = threading.Lock()

    threading.Thread(
        target=_worker,
        args=(task_queue, client, collectors, cfg.artifacts_dir,
              stop_events, active_tasks, control_lock),
        daemon=True,
    ).start()

    logger.info("agent %s starting (server=%s, perf_event=%s)",
                cfg.agent_id, cfg.server_url, cfg.perf_event)

    while True:
        interval = cfg.heartbeat_interval_sec
        try:
            with control_lock:
                active_snapshot = sorted(active_tasks)
            payload = {
                "agent_id": cfg.agent_id,
                "hostname": cfg.hostname,
                "ip_addr": cfg.ip_addr,
                "agent_version": cfg.agent_version,
                "self_stats": sampler.sample(),
                "discovery": discovery.get(),
                "active_task_ids": active_snapshot,
            }
            resp = client.heartbeat(payload)
            interval = resp.get("heartbeat_interval_sec", interval)
            for tid in resp.get("stop_task_ids", []):
                with control_lock:
                    stop_events.setdefault(tid, threading.Event()).set()
                logger.info("stop requested for continuous task %s", tid)
            task = resp.get("task")
            if task:
                logger.info("claimed task %s (pid=%s, %s)",
                            task["tid"], task["target_pid"], task["profiler_type"])
                with control_lock:
                    active_tasks.add(task["tid"])
                    stop_events.setdefault(task["tid"], threading.Event())
                task_queue.put(task)
        except Exception as exc:  # heartbeat must survive transient server/network errors
            logger.warning("heartbeat failed: %s", exc)
        time.sleep(interval)


if __name__ == "__main__":
    main()

"""End-to-end tests against a running stack (`make up` first).

Three paths:
  1. happy   : profile the demo workload -> task DONE + analysis DONE + flamegraph served
  2. bad pid : profile a nonexistent PID -> task FAILED with a reason
  3. offline : stop the agent -> it is marked offline, then recovers when restarted

Skipped automatically if the server is not reachable.
"""
import os
import subprocess
import time

import pytest
import requests

BASE = os.environ.get("MINIDROP_BASE", "http://localhost:8000")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def _server_up() -> bool:
    try:
        return requests.get(f"{BASE}/healthz", timeout=2).status_code == 200
    except requests.RequestException:
        return False


pytestmark = pytest.mark.skipif(not _server_up(), reason="stack not running (run `make up`)")


def _wait(predicate, timeout, interval=2.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    return last


def _create_task(pid: int, profiler: str = "pyspy") -> str:
    r = requests.post(f"{BASE}/api/v1/tasks", json={
        "name": "e2e", "target_pid": pid, "duration_sec": 6,
        "frequency_hz": 99, "profiler_type": profiler,
    }, timeout=10)
    r.raise_for_status()
    return r.json()["tid"]


def _task(tid: str) -> dict:
    return requests.get(f"{BASE}/api/v1/tasks/{tid}", timeout=10).json()


def _workload_pid() -> int:
    out = subprocess.check_output(
        ["docker", "inspect", "-f", "{{.State.Pid}}", "minidrop-workload"], text=True
    ).strip()
    return int(out)


def test_happy_path_produces_flamegraph():
    pid = _workload_pid()
    tid = _create_task(pid, "pyspy")

    done = _wait(lambda: _task(tid).get("status") in ("DONE", "FAILED"), timeout=90)
    detail = _task(tid)
    assert detail["status"] == "DONE", f"collection failed: {detail.get('status_reason')}"

    analyzed = _wait(lambda: _task(tid).get("analysis_status") in ("DONE", "FAILED"), timeout=60)
    detail = _task(tid)
    assert detail["analysis_status"] == "DONE", detail.get("analysis_reason")

    flame = detail["result_files"].get("flamegraph")
    assert flame
    r = requests.get(f"{BASE}/api/v1/tasks/{tid}/artifacts/{flame}", timeout=10)
    assert r.status_code == 200 and r.text.startswith("<svg")


def test_bad_pid_fails_with_reason():
    tid = _create_task(999999, "pyspy")
    _wait(lambda: _task(tid).get("status") == "FAILED", timeout=60)
    detail = _task(tid)
    assert detail["status"] == "FAILED"
    assert detail["status_reason"] or detail["error_message"]


def test_agent_offline_then_recover():
    def any_online():
        return any(a["online"] for a in requests.get(f"{BASE}/api/v1/agents", timeout=10).json())

    assert _wait(any_online, timeout=30), "no agent online at start"

    subprocess.run(["docker", "compose", "stop", "agent"], cwd=ROOT, check=True)
    try:
        # offline_threshold (30s) + monitor interval -> give it 50s
        went_offline = _wait(lambda: not any_online(), timeout=50)
        assert went_offline, "agent was not marked offline after being stopped"
    finally:
        subprocess.run(["docker", "compose", "start", "agent"], cwd=ROOT, check=True)

    assert _wait(any_online, timeout=40), "agent did not recover after restart"

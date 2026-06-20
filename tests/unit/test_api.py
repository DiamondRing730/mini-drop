"""API-level tests driving the real FastAPI app over SQLite (no Docker/Postgres needed).

Covers the routers, the heartbeat+claim path, result reporting and the analysis hand-off.
Each task is pinned to a unique agent_id so claims never cross between tests.
"""
import os

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture(scope="module")
def client():
    # `with` runs the lifespan: create_all on SQLite + start the monitor.
    with TestClient(app) as c:
        yield c


def _create(client, agent_id, pid=123, profiler="pyspy"):
    r = client.post("/api/v1/tasks", json={
        "target_pid": pid, "duration_sec": 5, "frequency_hz": 99,
        "profiler_type": profiler, "agent_id": agent_id,
    })
    assert r.status_code == 200, r.text
    return r.json()["tid"]


def test_healthz(client):
    assert client.get("/healthz").json()["status"] == "ok"


def test_create_and_list(client):
    tid = _create(client, agent_id="lister")
    listed = client.get("/api/v1/tasks").json()
    assert any(t["tid"] == tid and t["status"] == "PENDING" for t in listed)


def test_full_flow_create_to_analysis(client):
    tid = _create(client, agent_id="flow")

    # heartbeat claims the task and flips it to RUNNING
    hb = client.post("/api/v1/agent/heartbeat", json={
        "agent_id": "flow", "hostname": "h1", "ip_addr": "10.0.0.1",
        "self_stats": {"cpu_pct": 1.0},
    }).json()
    assert hb["task"] is not None and hb["task"]["tid"] == tid

    # agent reports UPLOADING then a successful result
    client.post(f"/api/v1/agent/tasks/{tid}/status", json={"status": "UPLOADING", "reason": "storing"})
    client.post(f"/api/v1/agent/tasks/{tid}/result", json={
        "success": True, "result_files": {"pyspy_folded": "pyspy.folded"},
    })

    detail = client.get(f"/api/v1/tasks/{tid}").json()
    assert detail["status"] == "DONE"
    assert detail["analysis_status"] == "PENDING"
    assert [t["to_status"] for t in detail["transitions"]] == ["PENDING", "RUNNING", "UPLOADING", "DONE"]

    # analyzer claims it
    nxt = client.get("/api/v1/internal/analysis/next").json()
    assert nxt["task"]["tid"] == tid
    client.post(f"/api/v1/internal/analysis/{tid}/result", json={
        "success": True, "analysis_files": {"flamegraph": "flamegraph.svg"},
    })
    assert client.get(f"/api/v1/tasks/{tid}").json()["analysis_status"] == "DONE"

    # SVG artifacts must render inside the Web iframe instead of downloading as files.
    out_dir = os.path.join(settings.artifacts_dir, tid)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "flamegraph.svg"), "w", encoding="utf-8") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    flame = client.get(f"/api/v1/tasks/{tid}/artifacts/flamegraph.svg")
    assert flame.status_code == 200
    assert flame.headers["content-type"].startswith("image/svg+xml")
    assert "content-disposition" not in flame.headers


def test_failed_collection_marks_failed(client):
    tid = _create(client, agent_id="failer")
    client.post("/api/v1/agent/heartbeat", json={"agent_id": "failer", "hostname": "h", "ip_addr": "1.1.1.1"})
    client.post(f"/api/v1/agent/tasks/{tid}/result", json={
        "success": False, "error_message": "target pid 123 does not exist",
    })
    detail = client.get(f"/api/v1/tasks/{tid}").json()
    assert detail["status"] == "FAILED"
    assert "does not exist" in detail["status_reason"]


def test_illegal_transition_returns_409(client):
    tid = _create(client, agent_id="nobody")  # stays PENDING
    r = client.post(f"/api/v1/agent/tasks/{tid}/status", json={"status": "UPLOADING", "reason": "x"})
    assert r.status_code == 409


def test_soft_delete(client):
    tid = _create(client, agent_id="deleter")
    assert client.delete(f"/api/v1/tasks/{tid}").status_code == 200
    assert client.get(f"/api/v1/tasks/{tid}").status_code == 404
    assert all(t["tid"] != tid for t in client.get("/api/v1/tasks").json())


def test_unknown_task_404(client):
    assert client.get("/api/v1/tasks/does-not-exist").status_code == 404


def test_continuous_chunks_timeline_and_window(client):
    r = client.post("/api/v1/tasks", json={
        "target_pid": 123, "duration_sec": 30, "frequency_hz": 99,
        "profiler_type": "pyspy", "mode": "continuous", "slice_sec": 5, "agent_id": "cont",
    })
    tid = r.json()["tid"]

    hb = client.post("/api/v1/agent/heartbeat", json={"agent_id": "cont", "hostname": "h", "ip_addr": "1.1.1.1"}).json()
    assert hb["task"]["mode"] == "continuous" and hb["task"]["slice_sec"] == 5

    # Lay down two slice files on the shared volume, then report them as chunks.
    cdir = os.path.join(settings.artifacts_dir, tid, "chunks")
    os.makedirs(cdir, exist_ok=True)
    with open(os.path.join(cdir, "c1.folded"), "w") as f:
        f.write("main;a 5\nmain;b 1\n")
    with open(os.path.join(cdir, "c2.folded"), "w") as f:
        f.write("main;a 3\n")
    client.post(f"/api/v1/agent/tasks/{tid}/chunk", json={"start_ts": 1000.0, "end_ts": 1005.0, "folded_file": "c1.folded", "samples": 6})
    client.post(f"/api/v1/agent/tasks/{tid}/chunk", json={"start_ts": 1005.0, "end_ts": 1010.0, "folded_file": "c2.folded", "samples": 3})

    timeline = client.get(f"/api/v1/tasks/{tid}/timeline").json()
    assert [e["samples"] for e in timeline] == [6, 3]

    # Window over both slices -> merged 5+1+3 = 9 samples.
    both = client.get(f"/api/v1/tasks/{tid}/window", params={"from": 900, "to": 1100})
    assert both.status_code == 200 and "9 samples" in both.text
    # Window over only the first slice -> 6 samples.
    first = client.get(f"/api/v1/tasks/{tid}/window", params={"from": 1000, "to": 1004})
    assert "6 samples" in first.text

    # Continuous result settles analysis to DONE without the analyzer.
    client.post(f"/api/v1/agent/tasks/{tid}/result", json={"success": True, "result_files": {"mode": "continuous", "chunks": "2"}})
    d = client.get(f"/api/v1/tasks/{tid}").json()
    assert d["status"] == "DONE" and d["analysis_status"] == "DONE"

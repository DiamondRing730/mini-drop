"""API-level tests driving the real FastAPI app over SQLite (no Docker/Postgres needed).

Covers the routers, the heartbeat+claim path, result reporting and the analysis hand-off.
Each task is pinned to a unique agent_id so claims never cross between tests.
"""
import pytest
from fastapi.testclient import TestClient

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

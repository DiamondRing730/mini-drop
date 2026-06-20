"""API-level tests driving the real FastAPI app over SQLite (no Docker/Postgres needed).

Covers the routers, the heartbeat+claim path, result reporting and the analysis hand-off.
Each task is pinned to a unique agent_id so claims never cross between tests.
"""
import json
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
    listed = client.get("/api/v1/tasks").json()["items"]
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
    assert all(t["tid"] != tid for t in client.get("/api/v1/tasks").json()["items"])


def test_task_list_search_filter_and_pagination(client):
    marker = "search-suite-unique"
    first = client.post("/api/v1/tasks", json={
        "name": f"{marker}-alpha", "target_pid": 41001, "profiler_type": "pyspy",
        "agent_id": "search-a",
    })
    second = client.post("/api/v1/tasks", json={
        "name": f"{marker}-beta", "target_pid": 41002, "profiler_type": "perf",
        "agent_id": "search-b",
    })
    assert first.status_code == 200 and second.status_code == 200

    page = client.get("/api/v1/tasks", params={"q": marker, "page": 1, "page_size": 1}).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert page["page"] == 1 and page["page_size"] == 1

    perf_only = client.get("/api/v1/tasks", params={
        "q": marker, "status": "PENDING", "profiler_type": "perf",
    }).json()
    assert perf_only["total"] == 1
    assert perf_only["items"][0]["target_pid"] == 41002


def test_retry_copies_finished_task_parameters(client):
    source = client.post("/api/v1/tasks", json={
        "name": "retry-source", "target_pid": 42001, "duration_sec": 17,
        "frequency_hz": 77, "profiler_type": "pyspy", "agent_id": "retry-agent",
    }).json()["tid"]
    assert client.post(f"/api/v1/tasks/{source}/retry").status_code == 409

    client.post("/api/v1/agent/heartbeat", json={
        "agent_id": "retry-agent", "hostname": "h", "ip_addr": "1.1.1.1",
    })
    client.post(f"/api/v1/agent/tasks/{source}/result", json={
        "success": False, "error_message": "synthetic failure",
    })
    retried = client.post(f"/api/v1/tasks/{source}/retry")
    assert retried.status_code == 200
    new_tid = retried.json()["tid"]
    detail = client.get(f"/api/v1/tasks/{new_tid}").json()
    assert detail["status"] == "PENDING"
    assert detail["name"] == "retry-source"
    assert detail["target_pid"] == 42001
    assert detail["duration_sec"] == 17 and detail["frequency_hz"] == 77
    assert detail["agent_id"] == "retry-agent"
    assert detail["status_reason"] == f"retried from task {source}"


def test_artifact_listing_and_nested_download(client):
    tid = _create(client, agent_id="artifacts")
    out_dir = os.path.join(settings.artifacts_dir, tid)
    nested = os.path.join(out_dir, "chunks")
    os.makedirs(nested, exist_ok=True)
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"ok": True}, f)
    with open(os.path.join(nested, "slice.folded"), "w", encoding="utf-8") as f:
        f.write("main;work 3\n")

    artifacts = client.get(f"/api/v1/tasks/{tid}/artifacts")
    assert artifacts.status_code == 200
    paths = {item["path"] for item in artifacts.json()}
    assert paths == {"summary.json", "chunks/slice.folded"}

    nested_file = client.get(f"/api/v1/tasks/{tid}/artifacts/chunks/slice.folded")
    assert nested_file.status_code == 200 and nested_file.text.strip() == "main;work 3"
    downloaded = client.get(f"/api/v1/tasks/{tid}/artifacts/summary.json", params={"download": True})
    assert "attachment" in downloaded.headers.get("content-disposition", "")


def _create_analyzed_profile(client, agent_id: str, name: str, hotspot: str, hotspot_samples: int):
    tid = client.post("/api/v1/tasks", json={
        "name": name, "target_pid": 43001, "duration_sec": 5,
        "frequency_hz": 99, "profiler_type": "pyspy", "agent_id": agent_id,
    }).json()["tid"]
    hb = client.post("/api/v1/agent/heartbeat", json={
        "agent_id": agent_id, "hostname": "h", "ip_addr": "1.1.1.1",
    }).json()
    assert hb["task"]["tid"] == tid
    client.post(f"/api/v1/agent/tasks/{tid}/status", json={"status": "UPLOADING", "reason": "done"})
    client.post(f"/api/v1/agent/tasks/{tid}/result", json={
        "success": True, "result_files": {"pyspy_folded": "pyspy.folded"},
    })
    claimed = client.get("/api/v1/internal/analysis/next").json()
    assert claimed["task"]["tid"] == tid

    other_samples = 100 - hotspot_samples
    tree = {
        "name": "pyspy all", "value": 100,
        "children": [{"name": "main", "value": 100, "children": [
            {"name": hotspot, "value": hotspot_samples, "children": []},
            {"name": "other_work", "value": other_samples, "children": []},
        ]}],
    }
    out_dir = os.path.join(settings.artifacts_dir, tid)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "tree.json"), "w", encoding="utf-8") as f:
        json.dump(tree, f)
    client.post(f"/api/v1/internal/analysis/{tid}/result", json={
        "success": True, "analysis_files": {"tree": "tree.json"},
    })
    return tid


def test_verified_before_after_comparison_api(client):
    baseline = _create_analyzed_profile(client, "compare-before", "before", "fib (workload.py:11)", 80)
    candidate = _create_analyzed_profile(client, "compare-after", "after", "fib (workload.py:12)", 20)
    response = client.post(f"/api/v1/tasks/{candidate}/comparison", json={"baseline_tid": baseline})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["verdict"] == "hotspot_reduced"
    assert report["verification"]["failed"] == 0
    fib = next(row for row in report["functions"] if row["function"] == "fib")
    assert fib["baseline_pct"] == 80.0 and fib["candidate_pct"] == 20.0

    artifacts = client.get(f"/api/v1/tasks/{candidate}/artifacts").json()
    paths = {item["path"] for item in artifacts}
    assert report["artifacts"]["report"] in paths
    assert report["artifacts"]["diff_flamegraph"] in paths
    flame = client.get(
        f"/api/v1/tasks/{candidate}/artifacts/{report['artifacts']['diff_flamegraph']}"
    )
    assert flame.status_code == 200 and flame.text.startswith("<svg")


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


def test_attribution_backend_is_explicitly_selected(client, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    tid = _create(client, agent_id="attribution")
    client.post("/api/v1/agent/heartbeat", json={
        "agent_id": "attribution", "hostname": "h", "ip_addr": "1.1.1.1",
    })
    client.post(f"/api/v1/agent/tasks/{tid}/status", json={
        "status": "UPLOADING", "reason": "storing",
    })
    client.post(f"/api/v1/agent/tasks/{tid}/result", json={
        "success": True, "result_files": {"pyspy_folded": "pyspy.folded"},
    })

    nxt = client.get("/api/v1/internal/analysis/next").json()
    assert nxt["task"]["tid"] == tid
    out_dir = os.path.join(settings.artifacts_dir, tid)
    os.makedirs(out_dir, exist_ok=True)
    tree = {
        "name": "pyspy all", "value": 100,
        "children": [{"name": "hot_func", "value": 100, "children": []}],
    }
    with open(os.path.join(out_dir, "tree.json"), "w", encoding="utf-8") as f:
        json.dump(tree, f)
    client.post(f"/api/v1/internal/analysis/{tid}/result", json={
        "success": True, "analysis_files": {"tree": "tree.json"},
    })

    offline = client.post(f"/api/v1/tasks/{tid}/attribution", json={"engine": "offline"})
    assert offline.status_code == 200
    assert offline.json()["engine"] == "offline"

    deepseek = client.post(f"/api/v1/tasks/{tid}/attribution", json={"engine": "deepseek"})
    assert deepseek.status_code == 503
    assert "DEEPSEEK_API_KEY" in deepseek.json()["detail"]

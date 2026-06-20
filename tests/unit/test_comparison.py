from app.attribution.profile import Profile, _walk
from app.comparison import compare_profiles, render_diff_flamegraph, verify_comparison


def _profile(tid: str, fib: int, crunch: int, io: int = 0) -> Profile:
    children = [
        {"name": "fib (workload.py:11)", "value": fib, "children": []},
        {"name": "crunch_numbers (workload.py:17)", "value": crunch, "children": []},
    ]
    if io:
        children.append({"name": "read_batch (workload.py:30)", "value": io, "children": []})
    total = fib + crunch + io
    tree = {
        "name": "pyspy all", "value": total,
        "children": [{"name": "main (workload.py:40)", "value": total, "children": children}],
    }
    prof = Profile(tid=tid, profiler="pyspy", total_samples=total, tree=tree)
    for child in tree["children"]:
        _walk(child, None, prof)
    return prof


def test_comparison_detects_primary_hotspot_reduction():
    baseline = _profile("before", fib=70, crunch=30)
    candidate = _profile("after", fib=20, crunch=20, io=60)
    report = compare_profiles(baseline, candidate)
    assert report["verdict"] == "hotspot_reduced"
    assert report["primary_hotspot"]["function"] == "fib"
    fib = next(row for row in report["functions"] if row["function"] == "fib")
    assert fib["baseline_pct"] == 70.0
    assert fib["candidate_pct"] == 20.0
    assert fib["delta_pct"] == -50.0
    assert fib["status"] == "improved"


def test_comparison_verifier_rejects_tampered_delta():
    baseline = _profile("before", fib=70, crunch=30)
    candidate = _profile("after", fib=20, crunch=80)
    rows = compare_profiles(baseline, candidate)["functions"]
    assert verify_comparison(baseline, candidate, rows)["failed"] == 0
    rows[0]["delta_pct"] += 9
    verified = verify_comparison(baseline, candidate, rows)
    assert verified["failed"] == 1
    assert verified["checks"][0]["verdict"] == "fail"


def test_diff_flamegraph_contains_verified_before_after_tooltips():
    baseline = _profile("before", fib=70, crunch=30)
    candidate = _profile("after", fib=20, crunch=80)
    svg = render_diff_flamegraph(baseline, candidate, "before -> after")
    assert svg.startswith("<svg")
    assert "优化前 70.00% / 优化后 20.00% / Δ -50.00pp" in svg
    assert "#4ade80" in svg  # improved frame
    assert "#f87171" in svg  # regressed frame

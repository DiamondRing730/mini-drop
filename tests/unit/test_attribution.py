"""Unit tests for AI smart attribution: profile derivation, tools, heuristic engine, verifier.

These exercise the deterministic path end-to-end (no network / no API key), which is the
path that always runs in CI and in an offline demo. The Claude tool-use loop shares the
exact same tools and result shape, so verifying the heuristic path validates the contract
the LLM path produces too.
"""
import json

from app.attribution.engine import attribute
from app.attribution.profile import Profile, hot_path, top_functions
from app.attribution.tools import TOOL_DEFS, dispatch
from app.attribution.verifier import verify


def _profile_from_tree() -> Profile:
    """A small but realistic call tree: main -> {fib (hot leaf), warm_path -> crunch}."""
    tree = {
        "name": "pyspy all",
        "value": 100,
        "children": [
            {"name": "main", "value": 100, "children": [
                {"name": "fib", "value": 60, "children": [
                    {"name": "fib", "value": 25, "children": []},  # recursive self
                ]},
                {"name": "warm_path", "value": 40, "children": [
                    {"name": "crunch_numbers", "value": 38, "children": []},
                ]},
            ]},
        ],
    }
    prof = Profile(tid="t1", profiler="pyspy", total_samples=0)
    from app.attribution.profile import _walk
    prof.tree = tree
    prof.total_samples = int(tree["value"])
    for child in tree["children"]:
        _walk(child, None, prof)
    return prof


def test_self_time_excludes_children():
    prof = _profile_from_tree()
    # main has value 100 but all of it flows to children -> 0 self.
    assert "main" not in prof.self_samples or prof.self_samples.get("main", 0) == 0
    # fib: top frame value 60, of which 25 goes to the recursive child -> 35 self there,
    # plus the leaf fib (25) contributes 25 -> 60 total self for the fib function.
    assert prof.self_samples["fib"] == 60
    # crunch_numbers is a pure leaf: all 38 is self.
    assert prof.self_samples["crunch_numbers"] == 38


def test_top_functions_ranked_by_self():
    prof = _profile_from_tree()
    tops = top_functions(prof, 3)
    assert tops[0]["func"] == "fib"
    assert tops[0]["self_pct"] == 60.0
    assert tops[0]["self_samples"] == 60


def test_hot_path_follows_fattest_child():
    prof = _profile_from_tree()
    path = [p["func"] for p in hot_path(prof)]
    # main -> fib (60 > 40) -> fib (recursive)
    assert path[0] == "main"
    assert path[1] == "fib"


def test_tools_dispatch_summary_and_callers():
    prof = _profile_from_tree()
    summary = json.loads(dispatch("get_profile_summary", {}, prof))
    assert summary["total_samples"] == 100
    assert summary["has_call_tree"] is True

    callers = json.loads(dispatch("get_function_callers", {"func": "crunch_numbers"}, prof))
    assert callers["callers"][0]["caller"] == "warm_path"


def test_tool_defs_include_submit():
    names = {t["name"] for t in TOOL_DEFS}
    assert "submit_attribution" in names
    assert "get_top_functions" in names


def test_heuristic_engine_produces_verified_findings():
    prof = _profile_from_tree()
    result = attribute(prof)  # no API key in test env -> deterministic path
    assert result["engine"] == "heuristic"
    assert result["findings"], "should produce at least one finding"
    assert result["findings"][0]["function"] == "fib"
    # The tool trace proves the engine only saw the profile through the tools.
    assert any(t["tool"] == "get_top_functions" for t in result["tool_trace"])


def test_verifier_passes_truthful_findings():
    prof = _profile_from_tree()
    result = attribute(prof)
    report = verify(prof, result["findings"])
    assert report["failed"] == 0
    assert report["verified"] == report["total_findings"] > 0


def test_verifier_rejects_hallucinated_function():
    prof = _profile_from_tree()
    bogus = [{"function": "nonexistent_func", "self_pct": 99.0, "evidence": "x", "recommendation": "y"}]
    report = verify(prof, bogus)
    assert report["failed"] == 1
    assert report["checks"][0]["verdict"] == "fail"
    assert "not a self-time hotspot" in report["checks"][0]["note"]


def test_verifier_rejects_wrong_percentage():
    prof = _profile_from_tree()
    # fib is real at 60%, but claim 90% -> outside tolerance -> fail.
    bad = [{"function": "fib", "self_pct": 90.0, "evidence": "x", "recommendation": "y"}]
    report = verify(prof, bad)
    assert report["failed"] == 1
    assert "profile shows 60.0%" in report["checks"][0]["note"]


def test_empty_profile_attributes_gracefully():
    prof = Profile(tid="empty", profiler="pyspy", total_samples=0)
    result = attribute(prof)
    assert result["findings"] == []
    report = verify(prof, result["findings"])
    assert report["total_findings"] == 0

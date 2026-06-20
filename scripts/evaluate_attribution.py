#!/usr/bin/env python3
"""Reproducible benchmark for Mini-Drop attribution engines.

Offline mode has no third-party dependencies. DeepSeek mode uses DEEPSEEK_API_KEY from
the environment and may incur API usage; it is never selected implicitly.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))

from app.attribution.engine import AttributionBackendError, attribute  # noqa: E402
from app.attribution.profile import Profile, _walk  # noqa: E402
from app.attribution.verifier import verify  # noqa: E402


CASES = [
    ("recursive_cpu", "fib", "request_handler"),
    ("numeric_loop", "crunch_numbers", "service"),
    ("io_path", "read_batch", "load_dataset"),
    ("parsing_path", "parse_records", "import_job"),
]


def make_profile(case: str, hotspot: str, caller: str) -> Profile:
    tree = {
        "name": "pyspy all",
        "value": 100,
        "children": [{
            "name": "main",
            "value": 100,
            "children": [{
                "name": caller,
                "value": 75,
                "children": [{"name": hotspot, "value": 70, "children": []}],
            }, {
                "name": "background_work",
                "value": 25,
                "children": [],
            }],
        }],
    }
    prof = Profile(tid=case, profiler="pyspy", total_samples=100, tree=tree)
    for child in tree["children"]:
        _walk(child, None, prof)
    return prof


def evaluate(backend: str) -> dict:
    rows = []
    for case, expected, caller in CASES:
        prof = make_profile(case, expected, caller)
        result = attribute(prof, backend=backend)
        verification = verify(prof, result.get("findings", []))
        predicted = result["findings"][0]["function"] if result.get("findings") else None
        rows.append({
            "case": case,
            "expected_top_function": expected,
            "predicted_top_function": predicted,
            "top1_correct": predicted == expected,
            "verification_pass_rate": verification["pass_rate"],
            "has_recommendation": bool(
                result.get("findings") and result["findings"][0].get("recommendation")
            ),
            "used_profile_tools": any(
                t.get("tool") == "get_top_functions" for t in result.get("tool_trace", [])
            ),
        })

    total = len(rows)
    return {
        "backend": backend,
        "cases": total,
        "top1_accuracy_pct": round(sum(r["top1_correct"] for r in rows) / total * 100, 1),
        "verified_findings_pct": round(
            sum(r["verification_pass_rate"] for r in rows) / total, 1
        ),
        "recommendation_coverage_pct": round(
            sum(r["has_recommendation"] for r in rows) / total * 100, 1
        ),
        "tool_trace_coverage_pct": round(
            sum(r["used_profile_tools"] for r in rows) / total * 100, 1
        ),
        "details": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["offline", "deepseek"], default="offline")
    args = parser.parse_args()
    try:
        print(json.dumps(evaluate(args.backend), ensure_ascii=False, indent=2))
        return 0
    except AttributionBackendError as exc:
        print(json.dumps({"backend": args.backend, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

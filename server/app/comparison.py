"""Deterministic, independently verified before/after profile comparison."""
from __future__ import annotations

import re
from html import escape

from .attribution.profile import Profile

CHANGE_THRESHOLD_PCT = 1.0
VERIFY_TOLERANCE_PCT = 0.05
_LOCATION_SUFFIX = re.compile(r"\s+\([^()]*:\d+\)$")


def canonical_function(name: str) -> str:
    """Merge line-level frames such as ``fib (workload.py:10/11)`` into ``fib``."""
    return _LOCATION_SUFFIX.sub("", name).strip() or name


def _self_percentages(prof: Profile) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for original, samples in prof.self_samples.items():
        func = canonical_function(original)
        row = merged.setdefault(func, {"samples": 0, "aliases": []})
        row["samples"] += int(samples)
        if original not in row["aliases"]:
            row["aliases"].append(original)
    for row in merged.values():
        row["pct"] = prof.pct(row["samples"])
    return merged


def _status(delta: float) -> str:
    if delta <= -CHANGE_THRESHOLD_PCT:
        return "improved"
    if delta >= CHANGE_THRESHOLD_PCT:
        return "regressed"
    return "stable"


def compare_profiles(baseline: Profile, candidate: Profile, limit: int = 15) -> dict:
    """Compare normalized self-time distributions and produce a conservative report."""
    before = _self_percentages(baseline)
    after = _self_percentages(candidate)
    rows = []
    for func in set(before) | set(after):
        b = before.get(func, {"samples": 0, "pct": 0.0, "aliases": []})
        c = after.get(func, {"samples": 0, "pct": 0.0, "aliases": []})
        delta = round(float(c["pct"]) - float(b["pct"]), 2)
        relative = None if not b["pct"] else round(delta / float(b["pct"]) * 100, 1)
        rows.append({
            "function": func,
            "baseline_samples": b["samples"],
            "candidate_samples": c["samples"],
            "baseline_pct": b["pct"],
            "candidate_pct": c["pct"],
            "delta_pct": delta,
            "relative_change_pct": relative,
            "status": _status(delta),
            "baseline_aliases": b["aliases"],
            "candidate_aliases": c["aliases"],
        })

    rows.sort(key=lambda row: (-abs(row["delta_pct"]), -row["baseline_pct"], row["function"]))
    visible = rows[:limit]
    baseline_hotspot = max(rows, key=lambda row: row["baseline_pct"], default=None)
    if baseline_hotspot is None:
        verdict = "no_data"
        summary = "两个任务都没有可比较的函数自耗时数据。"
    else:
        delta = baseline_hotspot["delta_pct"]
        if delta <= -CHANGE_THRESHOLD_PCT:
            verdict = "hotspot_reduced"
            summary = (
                f"优化前首要热点 {baseline_hotspot['function']} 的自耗时占比从 "
                f"{baseline_hotspot['baseline_pct']}% 降至 {baseline_hotspot['candidate_pct']}%"
                f"（下降 {abs(delta)} 个百分点）。"
            )
        elif delta >= CHANGE_THRESHOLD_PCT:
            verdict = "hotspot_increased"
            summary = (
                f"优化前首要热点 {baseline_hotspot['function']} 的自耗时占比从 "
                f"{baseline_hotspot['baseline_pct']}% 升至 {baseline_hotspot['candidate_pct']}%"
                f"（上升 {delta} 个百分点）。"
            )
        else:
            verdict = "no_clear_change"
            summary = (
                f"优化前首要热点 {baseline_hotspot['function']} 的占比变化为 {delta} 个百分点，"
                "未达到显著变化阈值。"
            )

    confidence = "high" if min(baseline.total_samples, candidate.total_samples) >= 500 else (
        "medium" if min(baseline.total_samples, candidate.total_samples) >= 100 else "low"
    )
    return {
        "verdict": verdict,
        "summary": summary,
        "confidence": confidence,
        "change_threshold_pct": CHANGE_THRESHOLD_PCT,
        "primary_hotspot": baseline_hotspot,
        "functions": visible,
        "counts": {
            "improved": sum(row["status"] == "improved" for row in rows),
            "regressed": sum(row["status"] == "regressed" for row in rows),
            "stable": sum(row["status"] == "stable" for row in rows),
        },
        "limitations": [
            "该比较使用归一化自耗时占比，能够证明热点分布变化，但不能单独证明整体延迟或吞吐提升。",
            "两个任务应使用相同负载、相同采集器和接近的采样参数，否则结果只适合作为线索。",
        ],
    }


def verify_comparison(baseline: Profile, candidate: Profile, rows: list[dict]) -> dict:
    """Independently recompute every reported percentage and delta."""
    before = _self_percentages(baseline)
    after = _self_percentages(candidate)
    checks = []
    passed = 0
    for row in rows:
        func = row.get("function", "")
        actual_before = float(before.get(func, {"pct": 0.0})["pct"])
        actual_after = float(after.get(func, {"pct": 0.0})["pct"])
        actual_delta = round(actual_after - actual_before, 2)
        claimed = (
            float(row.get("baseline_pct", 0)),
            float(row.get("candidate_pct", 0)),
            float(row.get("delta_pct", 0)),
        )
        actual = (actual_before, actual_after, actual_delta)
        ok = all(abs(a - b) <= VERIFY_TOLERANCE_PCT for a, b in zip(claimed, actual))
        if ok:
            passed += 1
        checks.append({
            "function": func,
            "verdict": "pass" if ok else "fail",
            "claimed": {"baseline_pct": claimed[0], "candidate_pct": claimed[1], "delta_pct": claimed[2]},
            "actual": {"baseline_pct": actual[0], "candidate_pct": actual[1], "delta_pct": actual[2]},
            "note": "前后占比及差值均已由原始profile复算" if ok else "报告数值与原始profile复算结果不一致",
        })
    total = len(checks)
    return {
        "total": total,
        "verified": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total * 100, 1) if total else 0.0,
        "tolerance_pct": VERIFY_TOLERANCE_PCT,
        "checks": checks,
    }


def render_diff_flamegraph(baseline: Profile, candidate: Profile, title: str, width: int = 1200) -> str:
    """Render the candidate stack layout, colored by change versus the baseline path."""
    if not candidate.tree:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="80"><text x="20" y="40">no candidate call tree</text></svg>'

    def path_pcts(prof: Profile) -> dict[tuple[str, ...], float]:
        result: dict[tuple[str, ...], float] = {}
        if not prof.tree:
            return result
        stack = [(prof.tree, tuple())]
        while stack:
            node, parent_path = stack.pop()
            path = parent_path + (node.get("name", ""),)
            result[path] = prof.pct(int(node.get("value", 0)))
            for child in node.get("children", []) or []:
                stack.append((child, path))
        return result

    baseline_pcts = path_pcts(baseline)
    total = candidate.total_samples or 1
    frame_h, min_width, pad = 18, 0.3, 48
    rects = []
    max_depth = 0
    stack = [(candidate.tree, 0.0, 0, tuple())]
    while stack:
        node, x, depth, parent_path = stack.pop()
        path = parent_path + (node.get("name", ""),)
        value = int(node.get("value", 0))
        w = value / total * width
        max_depth = max(max_depth, depth)
        if w >= min_width:
            candidate_pct = round(value / total * 100, 2)
            baseline_pct = baseline_pcts.get(path, 0.0)
            rects.append((x, depth, w, node.get("name", ""), baseline_pct, candidate_pct))
        child_x = x
        for child in node.get("children", []) or []:
            child_w = int(child.get("value", 0)) / total * width
            if child_w >= min_width:
                stack.append((child, child_x, depth + 1, path))
            child_x += child_w

    height = (max_depth + 1) * frame_h + pad + 28
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="Verdana,sans-serif" font-size="12">',
        f'<rect width="{width}" height="{height}" fill="#fff"/>',
        f'<text x="{width // 2}" y="18" text-anchor="middle" font-size="15" font-weight="bold">{escape(title)}</text>',
        '<text x="18" y="38" fill="#15803d">绿色=占比下降（改善）</text>',
        '<text x="210" y="38" fill="#b91c1c">红色=占比上升（恶化）</text>',
        '<text x="405" y="38" fill="#6b7280">灰色=变化不显著</text>',
    ]
    for x, depth, w, name, before, after in rects:
        delta = round(after - before, 2)
        if delta <= -CHANGE_THRESHOLD_PCT:
            color = "#4ade80"
        elif delta >= CHANGE_THRESHOLD_PCT:
            color = "#f87171"
        else:
            color = "#cbd5e1"
        y = height - (depth + 1) * frame_h - 4
        label = ""
        if w > 35:
            max_chars = int(w / 7)
            shown = name if len(name) <= max_chars else name[:max(0, max_chars - 1)] + "…"
            label = f'<text x="{x + 2:.1f}" y="{y + 12}" pointer-events="none">{escape(shown)}</text>'
        parts.append(
            f'<g><title>{escape(name)} — 优化前 {before:.2f}% / 优化后 {after:.2f}% / Δ {delta:+.2f}pp</title>'
            f'<rect x="{x:.2f}" y="{y}" width="{max(w, 0.4):.2f}" height="{frame_h - 1}" fill="{color}" stroke="#fff" stroke-width="0.5"/>{label}</g>'
        )
    parts.append("</svg>")
    return "".join(parts)

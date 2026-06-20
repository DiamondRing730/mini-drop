"""Independent verifier: re-check each attribution finding against the raw profile.

The engine (LLM or heuristic) produces findings that cite a function and a self_pct.
This module recomputes those numbers straight from the Profile — bypassing the engine
entirely — and grades each finding pass/fail. A hallucinated function or a wrong
percentage cannot survive: it simply doesn't match the data. The output is the
"evaluation report" the task asks for, attached to every attribution.
"""
from .profile import Profile

# A reported self_pct is accepted if it's within this many percentage points of the
# value recomputed from the profile (small tolerance for rounding on either side).
PCT_TOLERANCE = 1.0


def verify(prof: Profile, findings: list[dict]) -> dict:
    """Grade each finding against the profile. Returns the eval report."""
    checks = []
    passed = 0
    for f in findings:
        func = f.get("function", "")
        claimed = f.get("self_pct")
        notes = []
        ok = True

        actual_self = prof.self_samples.get(func)
        if actual_self is None:
            ok = False
            notes.append(f"函数 '{func}' 不是 profile 中的自耗时热点")
            actual_pct = None
        else:
            actual_pct = prof.pct(actual_self)
            if claimed is None:
                ok = False
                notes.append("未给出 self_pct")
            elif abs(float(claimed) - actual_pct) > PCT_TOLERANCE:
                ok = False
                notes.append(
                    f"声称 {claimed}%，但 profile 实测为 {actual_pct}%"
                    f"（{actual_self}/{prof.total_samples} 采样）"
                )
            else:
                notes.append(f"已核实：自耗时 {actual_pct}%（{actual_self} 采样）")

        if ok:
            passed += 1
        checks.append({
            "function": func,
            "claimed_self_pct": claimed,
            "actual_self_pct": actual_pct,
            "verdict": "pass" if ok else "fail",
            "note": "; ".join(notes),
        })

    total = len(checks)
    return {
        "total_findings": total,
        "verified": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total * 100, 1) if total else 0.0,
        "tolerance_pct": PCT_TOLERANCE,
        "checks": checks,
    }

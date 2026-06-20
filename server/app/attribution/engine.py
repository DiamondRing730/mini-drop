"""Attribution engine with two explicitly selected backends.

``offline`` is deterministic and always available. ``deepseek`` runs a real function-
calling loop and requires a configured API key. Both use the same read-only tools and
the verifier independently checks every reported hotspot percentage.
"""
import json
import os

from .deepseek import DeepSeekError, run_deepseek
from .profile import Profile, hot_path, top_functions
from .tools import dispatch


class AttributionResult(dict):
    """{engine, summary, findings:[...], tool_trace:[...], model?}. A dict for trivial JSON."""


class AttributionBackendError(RuntimeError):
    """The explicitly requested attribution backend could not produce a result."""


def _run_offline(prof: Profile) -> AttributionResult:
    """Deterministic analyst: walks the same tools, builds the same structured findings.

    Ranks by self-time, attributes each hotspot to its dominant caller, and tags whether
    it sits on the hottest path — mirroring what a competent engineer reads off a flamegraph.
    """
    tool_trace = [{"tool": "get_profile_summary", "input": {}}]
    summary_obj = json.loads(dispatch("get_profile_summary", {}, prof))

    tool_trace.append({"tool": "get_top_functions", "input": {"n": 5}})
    tops = top_functions(prof, 5)

    tool_trace.append({"tool": "get_hot_path", "input": {}})
    path = hot_path(prof)
    on_path = {p["func"] for p in path}

    findings = []
    for row in tops[:3]:
        func = row["func"]
        tool_trace.append({"tool": "get_function_callers", "input": {"func": func}})
        callers = prof.callers_of.get(func, {})
        top_caller = max(callers.items(), key=lambda kv: kv[1])[0] if callers else None

        evidence_bits = [f"{func} 自耗时占比 {row['self_pct']}%"]
        if top_caller:
            evidence_bits.append(f"主要由 {top_caller} 调入")
        if func in on_path:
            evidence_bits.append("位于最热的 root->leaf 调用路径上")

        findings.append({
            "function": func,
            "self_pct": row["self_pct"],
            "evidence": "；".join(evidence_bits) + "。",
            "recommendation": _recommend(func, top_caller),
        })

    hottest = findings[0]["function"] if findings else "无明显热点函数"
    pct = findings[0]["self_pct"] if findings else 0
    summary = (
        f"共 {summary_obj['total_samples']} 个采样、{summary_obj['distinct_functions']} 个函数；"
        f"时间集中在 {hottest}（自耗时 {pct}%）"
        + (f"，调用路径为 {' -> '.join(p['func'] for p in path[:4])}。" if path else "。")
    )
    return AttributionResult(
        engine="offline", summary=summary, findings=findings, tool_trace=tool_trace,
    )


def _recommend(func: str, caller: str | None) -> str:
    """A concrete, function-specific optimization hint (heuristic path)."""
    via = f"主要调用点是 {caller}；" if caller else ""
    low = func.lower()
    if "fib" in low or "recur" in low:
        return (f"{func} 占据大量自耗时，疑似朴素递归。{via}"
                "建议加记忆化（memoization）或改写为迭代，消除重复调用。")
    if any(k in low for k in ("loop", "crunch", "compute", "warm", "calc")):
        return (f"{func} 在紧密循环里属 CPU 密集型。{via}"
                "建议向量化、把循环不变量外提，或缓存中间结果。")
    if any(k in low for k in ("read", "write", "io", "fetch", "load", "query")):
        return (f"{func} 的时间主要花在 I/O 上。{via}"
                "建议批量化调用、增加缓存，或把该工作移出热点路径。")
    return (f"{func} 是自耗时最高的函数。{via}"
            "建议单独 profile 它，优化其内部逻辑或调用频率。")


def attribute(prof: Profile, backend: str = "offline") -> AttributionResult:
    """Run exactly the backend selected by the user; never silently fall back."""
    if backend not in {"offline", "deepseek"}:
        raise AttributionBackendError(f"unsupported attribution backend: {backend}")
    if prof.total_samples <= 0 or not prof.self_samples:
        return AttributionResult(
            engine=backend, summary="没有可供归因的 profile 数据。",
            findings=[], tool_trace=[],
        )
    if backend == "offline":
        return _run_offline(prof)
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise AttributionBackendError("DeepSeek 未配置：请在 .env 中设置 DEEPSEEK_API_KEY")
    try:
        return AttributionResult(**run_deepseek(prof))
    except DeepSeekError as exc:
        raise AttributionBackendError(str(exc)) from exc

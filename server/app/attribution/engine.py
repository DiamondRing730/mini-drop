"""Attribution engine: a constrained tool-calling analyst over a profile.

Two execution paths produce the same shape of result (`AttributionResult`):

1. LLM path (when ANTHROPIC_API_KEY is set and the `anthropic` SDK is importable):
   a real manual tool-use loop on Claude. The model may ONLY see the profile through
   the read-only tools in tools.py; it ends by calling `submit_attribution`. This is the
   "LLM can only call user-defined tools" requirement.

2. Heuristic path (no key / SDK / network): a deterministic analyst that calls the same
   tools and fills in the same structured findings. Guarantees the feature is always
   demoable offline and adds no hard dependency to the build.

Either way the verifier (verifier.py) independently re-checks the numbers, so the engine
output is never trusted blind.
"""
import json
import logging
import os

from .deepseek import run_deepseek
from .profile import Profile, hot_path, top_functions
from .tools import SYSTEM_PROMPT, TOOL_DEFS, dispatch

logger = logging.getLogger("minidrop.attribution")

MODEL = "claude-opus-4-8"
MAX_TOOL_ITERATIONS = 12


class AttributionResult(dict):
    """{engine, summary, findings:[...], tool_trace:[...], model?}. A dict for trivial JSON."""


def _run_claude(prof: Profile) -> AttributionResult | None:
    """Real Claude tool-use loop. Returns None if the SDK/key/network is unavailable."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        return None

    client = anthropic.Anthropic()
    messages = [{
        "role": "user",
        "content": (
            f"Analyze the profile for task {prof.tid} (profiler: {prof.profiler}). "
            "Find the CPU/latency root cause and propose optimizations. "
            "Inspect it only through the tools, then call submit_attribution."
        ),
    }]
    tool_trace: list[dict] = []

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            resp = client.messages.create(
                model=MODEL,
                max_tokens=16000,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                tools=TOOL_DEFS,
                messages=messages,
            )
            if resp.stop_reason == "refusal":
                logger.warning("attribution refused by model for %s", prof.tid)
                return None

            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            if not tool_uses:
                # Model stopped without submitting — treat as no structured result.
                return None

            # Append the assistant turn verbatim (preserves thinking + tool_use blocks).
            messages.append({"role": "assistant", "content": resp.content})

            results = []
            for tu in tool_uses:
                if tu.name == "submit_attribution":
                    return AttributionResult(
                        engine="claude",
                        model=MODEL,
                        summary=tu.input.get("summary", ""),
                        findings=tu.input.get("findings", []),
                        tool_trace=tool_trace,
                    )
                try:
                    out = dispatch(tu.name, tu.input, prof)
                    tool_trace.append({"tool": tu.name, "input": tu.input})
                    results.append({"type": "tool_result", "tool_use_id": tu.id, "content": out})
                except Exception as exc:  # surface tool errors back to the model
                    results.append({
                        "type": "tool_result", "tool_use_id": tu.id,
                        "content": f"error: {exc}", "is_error": True,
                    })
            messages.append({"role": "user", "content": results})
        return None  # ran out of iterations without submitting
    except Exception as exc:
        logger.warning("claude attribution failed for %s: %s", prof.tid, exc)
        return None


def _run_heuristic(prof: Profile) -> AttributionResult:
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

        evidence_bits = [f"{row['self_pct']}% of samples are self-time in {func}"]
        if top_caller:
            evidence_bits.append(f"reached mainly via {top_caller}")
        if func in on_path:
            evidence_bits.append("sits on the hottest root->leaf path")

        findings.append({
            "function": func,
            "self_pct": row["self_pct"],
            "evidence": "; ".join(evidence_bits) + ".",
            "recommendation": _recommend(func, top_caller),
        })

    hottest = findings[0]["function"] if findings else "no dominant function"
    pct = findings[0]["self_pct"] if findings else 0
    summary = (
        f"{summary_obj['total_samples']} samples across {summary_obj['distinct_functions']} "
        f"functions. Time concentrates in {hottest} ({pct}% self-time)"
        + (f", reached via the path {' -> '.join(p['func'] for p in path[:4])}." if path else ".")
    )
    return AttributionResult(
        engine="heuristic", summary=summary, findings=findings, tool_trace=tool_trace,
    )


def _recommend(func: str, caller: str | None) -> str:
    """A concrete, function-specific optimization hint (heuristic path)."""
    via = f" The dominant call site is {caller}; " if caller else " "
    low = func.lower()
    if "fib" in low or "recur" in low:
        return (f"{func} dominates self-time; likely naive recursion." + via
                + "memoize or convert to an iterative form to cut redundant calls.")
    if any(k in low for k in ("loop", "crunch", "compute", "warm", "calc")):
        return (f"{func} is CPU-bound in a tight loop." + via
                + "vectorize, hoist invariant work out of the loop, or cache results.")
    if any(k in low for k in ("read", "write", "io", "fetch", "load", "query")):
        return (f"{func} spends its time on I/O." + via
                + "batch the calls, add caching, or move the work off the hot path.")
    return (f"{func} is the top self-time consumer." + via
            + "profile it in isolation and optimize its inner work or call frequency.")


def attribute(prof: Profile) -> AttributionResult:
    """Run a real LLM if a key is configured, else the deterministic heuristic.

    Preference: DeepSeek (DEEPSEEK_API_KEY) -> Claude (ANTHROPIC_API_KEY) -> heuristic.
    All three drive the same read-only tools and produce the same result shape, and the
    verifier re-checks every number regardless of which backend ran.
    """
    if prof.total_samples <= 0 or not prof.self_samples:
        return AttributionResult(
            engine="heuristic", summary="No profile data to attribute.",
            findings=[], tool_trace=[],
        )
    ds = run_deepseek(prof)
    if ds is not None:
        return AttributionResult(**ds)
    return _run_claude(prof) or _run_heuristic(prof)

"""The custom tools the attribution analyst may call — its ONLY view of the profile.

Each tool is a pure read over a Profile (built in profile.py from the analyzer's
artifacts). The same definitions drive both the Claude tool-use loop and the
deterministic fallback engine, and the verifier re-derives every number the model
reports from these same accessors — so a claim that doesn't match the data fails.

`submit_attribution` is the terminal tool: the model calls it once to deliver its
structured conclusions, which ends the loop.
"""
import json

from .profile import Profile, hot_path, top_functions

# Shared system prompt for both LLM backends (Claude and DeepSeek). Lives here, next to
# the tool definitions it describes, so both engine.py and deepseek.py import it from one
# place without a circular import.
SYSTEM_PROMPT = """You are a performance-engineering analyst for the Mini-Drop profiler.
You are given a CPU/latency profile of a program and must find the root cause of where
time is being spent, then propose concrete optimizations.

You can ONLY inspect the profile through the provided tools -- you have no other view of
the data. Work like a profiler expert:
1. get_profile_summary to size the data.
2. get_top_functions to find the hottest functions by self-time.
3. get_hot_path to see where cost concentrates down the call stack.
4. get_function_callers on a hot function to attribute it to a responsible call site.
Then call submit_attribution exactly once with ranked findings.

Every finding must cite the function name and the self_pct you actually read from a tool --
those numbers are independently verified against the raw profile, so do not estimate or
invent them. Keep recommendations concrete and specific to the function named."""

# JSON-schema tool definitions sent to the Claude Messages API. Kept minimal and
# strict (no free-form data input) so the model cannot smuggle in numbers — it must
# read them through these tools.
TOOL_DEFS = [
    {
        "name": "get_profile_summary",
        "description": (
            "Get high-level profile metadata: profiler type, total samples, number of "
            "distinct functions. Call this first to understand the scale of the data."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_top_functions",
        "description": (
            "List the hottest functions ranked by self-time (time spent in the function "
            "itself, excluding callees). Each entry has self_samples, self_pct, total_samples, "
            "total_pct. Use this to identify CPU hotspots."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "description": "How many to return (1-20)."},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_hot_path",
        "description": (
            "Get the single heaviest root->leaf call path (at each level, the child holding "
            "the most samples). Shows where the dominant cost concentrates down the stack."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_function_callers",
        "description": (
            "For a given function, list which functions call into it and with how many samples. "
            "Use this to attribute a hotspot to the call site responsible for it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "func": {"type": "string", "description": "Exact function name."},
            },
            "required": ["func"],
            "additionalProperties": False,
        },
    },
    {
        "name": "submit_attribution",
        "description": (
            "Submit your final root-cause attribution. Call this exactly once when done. "
            "Each finding must cite the function and the self_pct you read from the tools so "
            "it can be independently verified against the profile."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "1-3 sentence plain-language diagnosis of where the time goes.",
                },
                "findings": {
                    "type": "array",
                    "description": "Ranked root-cause findings, hottest first.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "function": {"type": "string", "description": "The function responsible."},
                            "self_pct": {
                                "type": "number",
                                "description": "Self-time percentage you read from get_top_functions.",
                            },
                            "evidence": {
                                "type": "string",
                                "description": "Why this is a root cause (caller, hot path, etc.).",
                            },
                            "recommendation": {
                                "type": "string",
                                "description": "A concrete, actionable optimization suggestion.",
                            },
                        },
                        "required": ["function", "self_pct", "evidence", "recommendation"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["summary", "findings"],
            "additionalProperties": False,
        },
    },
]


class ToolError(Exception):
    pass


def dispatch(name: str, tool_input: dict, prof: Profile) -> str:
    """Execute one read-only tool against the profile; return a JSON string result.

    submit_attribution is handled by the engine (it ends the loop), not here.
    """
    if name == "get_profile_summary":
        return json.dumps({
            "profiler": prof.profiler,
            "total_samples": prof.total_samples,
            "distinct_functions": len(prof.total_of),
            "has_call_tree": prof.tree is not None,
        })

    if name == "get_top_functions":
        n = int(tool_input.get("n", 10))
        n = max(1, min(n, 20))
        return json.dumps(top_functions(prof, n))

    if name == "get_hot_path":
        return json.dumps(hot_path(prof))

    if name == "get_function_callers":
        func = tool_input.get("func", "")
        callers = prof.callers_of.get(func)
        if not callers:
            return json.dumps({"func": func, "callers": [], "note": "no callers recorded (root or unknown function)"})
        ranked = sorted(callers.items(), key=lambda kv: -kv[1])
        return json.dumps({
            "func": func,
            "callers": [{"caller": c, "samples": s, "pct": prof.pct(s)} for c, s in ranked],
        })

    raise ToolError(f"unknown tool {name}")

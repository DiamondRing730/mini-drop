"""DeepSeek backend for attribution — a real LLM tool-use loop over the same read-only tools.

DeepSeek's API is OpenAI-compatible (function calling), so this talks to it over stdlib
urllib (no new build dependency, no SDK). It drives the same read-only tools as the
offline path and ends with submit_attribution; the verifier re-checks every number.

Enabled when DEEPSEEK_API_KEY is set in the environment. The key is read from the env only —
never hardcoded — and injected into the container via a gitignored .env file.
"""
import json
import logging
import os
import urllib.error
import urllib.request

from .profile import Profile
from .tools import SYSTEM_PROMPT, TOOL_DEFS, dispatch

logger = logging.getLogger("minidrop.attribution")

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"  # V3 chat model with function calling
MAX_TOOL_ITERATIONS = 12
TIMEOUT_SEC = 60


class DeepSeekError(RuntimeError):
    """DeepSeek was selected but could not return a structured attribution."""


def _openai_tools() -> list[dict]:
    """Convert the shared TOOL_DEFS to OpenAI/DeepSeek function-calling shape."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in TOOL_DEFS
    ]


def _post(url: str, key: str, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_deepseek(prof: Profile) -> dict:
    """Run the DeepSeek tool-use loop or raise a user-facing backend error."""
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise DeepSeekError("DeepSeek 未配置：缺少 DEEPSEEK_API_KEY")
    base = os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL)
    url = f"{base}/chat/completions"
    tools = _openai_tools()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"Analyze the profile for task {prof.tid} (profiler: {prof.profiler}). "
            "Find the CPU/latency root cause and propose optimizations. "
            "Inspect it only through the tools, then call submit_attribution."
        )},
    ]
    tool_trace: list[dict] = []

    try:
        for _ in range(MAX_TOOL_ITERATIONS):
            data = _post(url, key, {
                "model": model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "max_tokens": 4096,
                "temperature": 0,  # OpenAI-compatible param; DeepSeek honors it for determinism
            })
            msg = data["choices"][0]["message"]
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                raise DeepSeekError("DeepSeek 未调用 submit_attribution，未生成结构化归因")

            # Echo the assistant turn verbatim (must include tool_calls for the protocol).
            messages.append({
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                fn = tc["function"]
                name = fn["name"]
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}

                if name == "submit_attribution":
                    return {
                        "engine": "deepseek",
                        "model": model,
                        "summary": args.get("summary", ""),
                        "findings": args.get("findings", []),
                        "tool_trace": tool_trace,
                    }

                try:
                    out = dispatch(name, args, prof)
                    tool_trace.append({"tool": name, "input": args})
                except Exception as exc:  # surface tool errors back to the model
                    out = f"error: {exc}"
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": out})
        raise DeepSeekError("DeepSeek 工具调用次数达到上限，未提交归因结果")
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        logger.warning("deepseek attribution failed for %s: %s", prof.tid, exc)
        raise DeepSeekError(f"DeepSeek 调用失败：{exc}") from exc

"""Read-only view over an analyzed profile.

Loads the analyzer's tree.json (full call tree) and top.json (hot leaves) for a task
and derives the metrics the attribution tools answer from: self-time per function,
the hottest root->leaf path, and caller/callee neighbourhoods. Everything here is a
pure function of the on-disk artifacts — no LLM, no mutation — which is exactly what
makes the verifier able to re-check the model's claims against the same numbers.
"""
import json
import os
from dataclasses import dataclass, field


@dataclass
class Profile:
    tid: str
    profiler: str
    total_samples: int
    # function name -> self samples (time spent in the function itself, leaf of a stack)
    self_samples: dict[str, int] = field(default_factory=dict)
    # function name -> total samples (function anywhere on the stack, incl. descendants)
    total_of: dict[str, int] = field(default_factory=dict)
    # function name -> {caller -> samples flowing in from that caller}
    callers_of: dict[str, dict[str, int]] = field(default_factory=dict)
    # function name -> {callee -> samples flowing out to that callee}
    callees_of: dict[str, dict[str, int]] = field(default_factory=dict)
    tree: dict | None = None  # the raw {name,value,children} root, for hot-path walking

    def pct(self, samples: int) -> float:
        denom = self.total_samples or 1
        return round(samples / denom * 100, 2)


def _walk(node: dict, parent: str | None, prof: Profile) -> None:
    """Accumulate total/self/caller/callee counts from a {name,value,children} node."""
    name = node["name"]
    value = int(node.get("value", 0))
    children = node.get("children", []) or []

    prof.total_of[name] = prof.total_of.get(name, 0) + value
    # self time = value not attributed to any child (time spent in this frame itself)
    child_sum = sum(int(c.get("value", 0)) for c in children)
    self_here = value - child_sum
    if self_here > 0:
        prof.self_samples[name] = prof.self_samples.get(name, 0) + self_here

    if parent is not None:
        prof.callers_of.setdefault(name, {})
        prof.callers_of[name][parent] = prof.callers_of[name].get(parent, 0) + value
        prof.callees_of.setdefault(parent, {})
        prof.callees_of[parent][name] = prof.callees_of[parent].get(name, 0) + value

    for child in children:
        _walk(child, name, prof)


def load_profile(artifacts_dir: str, tid: str, profiler: str, result_files: dict) -> Profile:
    """Build a Profile from the analyzer's tree.json (preferred) or top.json (fallback)."""
    out_dir = os.path.join(artifacts_dir, tid)
    prof = Profile(tid=tid, profiler=profiler, total_samples=0)

    tree_name = result_files.get("tree")
    if tree_name:
        tree_path = os.path.join(out_dir, os.path.basename(tree_name))
        try:
            with open(tree_path, encoding="utf-8") as f:
                tree = json.load(f)
            prof.tree = tree
            # The root's children are the real frames; the root itself ("<profiler> all")
            # holds the grand total but is not a function we attribute.
            prof.total_samples = int(tree.get("value", 0))
            for child in tree.get("children", []) or []:
                _walk(child, None, prof)
            return prof
        except (OSError, ValueError, KeyError):
            pass  # fall back to top.json below

    # Fallback: only TopN self-samples are available (no call structure).
    top_name = result_files.get("topn")
    if top_name:
        top_path = os.path.join(out_dir, os.path.basename(top_name))
        try:
            with open(top_path, encoding="utf-8") as f:
                top = json.load(f)
            prof.total_samples = int(top.get("total_samples", 0))
            for row in top.get("top", []):
                func = row.get("func", "")
                cnt = int(row.get("self", 0))
                if func:
                    prof.self_samples[func] = prof.self_samples.get(func, 0) + cnt
                    prof.total_of[func] = prof.total_of.get(func, 0) + cnt
        except (OSError, ValueError, KeyError):
            pass

    return prof


def top_functions(prof: Profile, n: int = 10) -> list[dict]:
    """Hottest functions by self-time, the way a profiler's flat view ranks them."""
    ranked = sorted(prof.self_samples.items(), key=lambda kv: -kv[1])[:n]
    return [
        {"func": func, "self_samples": cnt, "self_pct": prof.pct(cnt),
         "total_samples": prof.total_of.get(func, cnt), "total_pct": prof.pct(prof.total_of.get(func, cnt))}
        for func, cnt in ranked
    ]


def hot_path(prof: Profile) -> list[dict]:
    """The single heaviest root->leaf path: at each node, descend into the fattest child."""
    if not prof.tree:
        return []
    path: list[dict] = []
    node = prof.tree
    # skip the synthetic root frame
    children = node.get("children", []) or []
    while children:
        node = max(children, key=lambda c: int(c.get("value", 0)))
        path.append({
            "func": node["name"],
            "samples": int(node.get("value", 0)),
            "pct": prof.pct(int(node.get("value", 0))),
        })
        children = node.get("children", []) or []
    return path

"""Parse raw profiler output into folded stacks: {"a;b;c": sample_count}.

Two input shapes:
  - perf script text (from `perf script`): sample blocks separated by blank lines, each a
    header line + indented frame lines (leaf first). We reverse to root->leaf and prepend
    the command name. This is a Python reimplementation of stackcollapse-perf.pl's core, so
    the analyzer needs neither Perl nor the FlameGraph scripts.
  - py-spy raw / folded text: already "frame;frame;... count" per line.
"""


def parse_folded(path: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    with open(path, errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            idx = line.rfind(" ")
            if idx < 0:
                continue
            stack, raw_count = line[:idx], line[idx + 1:]
            try:
                count = int(raw_count)
            except ValueError:
                continue
            counts[stack] = counts.get(stack, 0) + count
    return counts


def parse_perf_script(path: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    comm: str | None = None
    frames: list[str] = []

    def flush() -> None:
        nonlocal comm, frames
        if comm and frames:
            stack = [comm] + list(reversed(frames))
            key = ";".join(stack)
            counts[key] = counts.get(key, 0) + 1
        comm, frames = None, []

    with open(path, errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.strip() == "":
                flush()
                continue
            if not (line.startswith(" ") or line.startswith("\t")):
                # New sample header, e.g. "python 1234 [000] 12.34: cpu-clock:"
                flush()
                toks = line.split()
                comm = toks[0] if toks else "unknown"
            else:
                toks = line.split()
                sym = toks[1] if len(toks) >= 2 else (toks[0] if toks else "[unknown]")
                frames.append(sym.split("+")[0])  # drop +offset
        flush()
    return counts


def build_tree(folded: dict[str, int], root_name: str = "all") -> dict:
    """Fold the stacks into a {name, value, children:[...]} tree (root is the total)."""
    root = {"name": root_name, "value": 0, "_children": {}}
    for stack, count in folded.items():
        root["value"] += count
        node = root
        for frame in stack.split(";"):
            child = node["_children"].get(frame)
            if child is None:
                child = {"name": frame, "value": 0, "_children": {}}
                node["_children"][frame] = child
            child["value"] += count
            node = child

    def finalize(node: dict) -> dict:
        children = [finalize(c) for c in sorted(node["_children"].values(), key=lambda n: n["name"])]
        return {"name": node["name"], "value": node["value"], "children": children}

    return finalize(root)


def compute_topn(folded: dict[str, int], n: int = 15) -> dict:
    """TopN hottest leaf functions by self-sample count."""
    self_counts: dict[str, int] = {}
    total = 0
    for stack, count in folded.items():
        total += count
        leaf = stack.split(";")[-1]
        self_counts[leaf] = self_counts.get(leaf, 0) + count
    ranked = sorted(self_counts.items(), key=lambda kv: -kv[1])[:n]
    denom = total or 1
    return {
        "total_samples": total,
        "unique_stacks": len(folded),
        "top": [
            {"func": func, "self": cnt, "self_pct": round(cnt / denom * 100, 2)}
            for func, cnt in ranked
        ],
    }

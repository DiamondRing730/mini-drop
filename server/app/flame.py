"""On-demand flamegraph assembly for continuous-profiling time windows.

Mirrors the analyzer's pure-Python folded->tree->SVG logic so the server can render the
flamegraph for ANY user-selected window by merging the folded chunks that overlap it, with
no round-trip to the analyzer. (Kept in sync with analyzer/analyzer/{stacks,flamegraph}.py.)
"""
from html import escape

FRAME_H = 16
MIN_WIDTH = 0.3
PAD = 24


def merge_folded_files(paths: list[str]) -> dict[str, int]:
    """Sum folded-stack counts across several chunk files."""
    counts: dict[str, int] = {}
    for path in paths:
        try:
            with open(path, errors="replace") as f:
                for line in f:
                    line = line.rstrip("\n")
                    if not line.strip():
                        continue
                    idx = line.rfind(" ")
                    if idx < 0:
                        continue
                    stack, raw = line[:idx], line[idx + 1:]
                    try:
                        c = int(raw)
                    except ValueError:
                        continue
                    counts[stack] = counts.get(stack, 0) + c
        except OSError:
            continue
    return counts


def build_tree(folded: dict[str, int], root_name: str = "all") -> dict:
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

    def finalize(n: dict) -> dict:
        children = [finalize(c) for c in sorted(n["_children"].values(), key=lambda x: x["name"])]
        return {"name": n["name"], "value": n["value"], "children": children}

    return finalize(root)


def _color(name: str) -> str:
    h = 0
    for ch in name:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    r = 60 + (h % 60)
    g = 120 + ((h >> 8) % 110)
    b = 180 + ((h >> 16) % 60)
    return f"rgb({r},{g},{b})"


def render_svg(tree: dict, title: str, width: int = 1200) -> str:
    total = tree["value"] or 1
    rects: list[tuple[float, int, float, str, int]] = []
    max_depth = 0
    stack = [(tree, 0.0, 0)]
    while stack:
        node, x, depth = stack.pop()
        w = node["value"] / total * width
        max_depth = max(max_depth, depth)
        if w >= MIN_WIDTH:
            rects.append((x, depth, w, node["name"], node["value"]))
        cx = x
        for child in node["children"]:
            cw = child["value"] / total * width
            if cw >= MIN_WIDTH:
                stack.append((child, cx, depth + 1))
            cx += cw

    height = (max_depth + 1) * FRAME_H + PAD + 30
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'font-family="Verdana, sans-serif" font-size="12">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{width // 2}" y="18" text-anchor="middle" font-size="15" '
        f'font-weight="bold">{escape(title)}</text>',
    ]
    for x, depth, w, name, value in rects:
        y = height - (depth + 1) * FRAME_H - 4
        pct = value / total * 100
        label = ""
        if w > 28:
            max_chars = int(w / 7)
            text = name if len(name) <= max_chars else name[: max(0, max_chars - 1)] + "…"
            label = f'<text x="{x + 2:.1f}" y="{y + 11}" pointer-events="none">{escape(text)}</text>'
        parts.append(
            f'<g><title>{escape(name)} — {value} samples ({pct:.2f}%)</title>'
            f'<rect x="{x:.2f}" y="{y}" width="{max(w, 0.4):.2f}" height="{FRAME_H - 1}" '
            f'fill="{_color(name)}" stroke="#ffffff" stroke-width="0.4"/>{label}</g>'
        )
    parts.append("</svg>")
    return "".join(parts)

"""Render a {name,value,children} tree into a standalone SVG flamegraph.

A dependency-free renderer: classic flame layout (root at the bottom, width ∝ samples),
deterministic warm/"python" palette, native tooltips via <title>. Frames narrower than
~0.3px are skipped (invisible anyway) to bound output size.
"""
from html import escape

FRAME_H = 16
MIN_WIDTH = 0.3  # px; frames thinner than this are not drawn
PAD = 24


def _color(name: str, scheme: str) -> str:
    h = 0
    for ch in name:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    if scheme == "python":
        # blue/green family for language-level (py-spy) graphs
        r = 60 + (h % 60)
        g = 120 + ((h >> 8) % 110)
        b = 180 + ((h >> 16) % 60)
    else:
        # warm "hot" family for perf graphs
        r = 205 + (h % 50)
        g = 50 + ((h >> 8) % 180)
        b = 40 + ((h >> 16) % 45)
    return f"rgb({r},{g},{b})"


def render_svg(tree: dict, title: str = "Flame Graph", width: int = 1200, scheme: str = "hot") -> str:
    total = tree["value"] or 1
    rects: list[tuple[float, int, float, str, int]] = []
    max_depth = 0

    # Iterative layout to avoid recursion limits on very deep stacks.
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
        fill = _color(name, scheme)
        label = ""
        if w > 28:  # only label frames wide enough to read
            max_chars = int(w / 7)
            text = name if len(name) <= max_chars else name[: max(0, max_chars - 1)] + "…"
            label = (f'<text x="{x + 2:.1f}" y="{y + 11}" '
                     f'pointer-events="none">{escape(text)}</text>')
        parts.append(
            f'<g><title>{escape(name)} — {value} samples ({pct:.2f}%)</title>'
            f'<rect x="{x:.2f}" y="{y}" width="{max(w, 0.4):.2f}" height="{FRAME_H - 1}" '
            f'fill="{fill}" stroke="#ffffff" stroke-width="0.4"/>{label}</g>'
        )
    parts.append("</svg>")
    return "".join(parts)

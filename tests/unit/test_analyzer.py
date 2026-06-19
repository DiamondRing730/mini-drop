"""Unit tests for the analyzer's stack parsing, tree building, TopN and SVG rendering."""
import os
import tempfile

from analyzer.ebpf import parse_bpftrace
from analyzer.flamegraph import render_svg
from analyzer.stacks import build_tree, compute_topn, parse_folded, parse_perf_script


def _write(text: str, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    return path


def test_parse_folded():
    path = _write("main;service;calc 30\nmain;service;io 10\nmain;idle 5\n", ".folded")
    folded = parse_folded(path)
    os.remove(path)
    assert folded == {"main;service;calc": 30, "main;service;io": 10, "main;idle": 5}


def test_parse_perf_script_reverses_and_prepends_comm():
    text = (
        "python 100 [000] 1.0: cpu-clock:\n"
        "\tffff aaa+0x1 (k)\n"
        "\tffff calc+0x2 (/a)\n"
        "\tffff main+0x3 (/a)\n"
        "\n"
        "python 100 [000] 2.0: cpu-clock:\n"
        "\tffff calc+0x2 (/a)\n"
        "\tffff main+0x3 (/a)\n"
    )
    path = _write(text, ".txt")
    folded = parse_perf_script(path)
    os.remove(path)
    # leaf-first frames get reversed and the command is prepended.
    assert folded == {"python;main;calc;aaa": 1, "python;main;calc": 1}


def test_build_tree_and_topn():
    folded = {"main;service;calc": 30, "main;service;io": 10, "main;idle": 5}
    tree = build_tree(folded, "all")
    assert tree["value"] == 45
    top = compute_topn(folded, 5)
    assert top["total_samples"] == 45
    assert top["top"][0]["func"] == "calc" and top["top"][0]["self"] == 30
    assert top["top"][0]["self_pct"] == round(30 / 45 * 100, 2)


def test_render_svg_is_wellformed():
    folded = {"main;service;calc": 30, "main;idle": 5}
    svg = render_svg(build_tree(folded, "all"), title="t", scheme="python")
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "calc" in svg and "35 samples" in svg  # root tooltip = total


def test_empty_input_yields_empty_folded():
    path = _write("\n  \n", ".folded")
    assert parse_folded(path) == {}
    os.remove(path)


def test_parse_bpftrace_histogram():
    text = (
        "Attaching 5 probes...\n\n"
        "@by_comm[python]: 12\n"
        "@by_comm[dd]: 5000\n\n"
        "@usecs:\n"
        "[0]                  3 |@@@        |\n"
        "[2, 4)               7 |@@@@@@@    |\n"
        "[4, 8)              42 |@@@@@@@@@@@|\n"
    )
    path = _write(text, ".txt")
    dist = parse_bpftrace(path)
    os.remove(path)
    assert dist["total_events"] == 52
    assert dist["by_comm"][0] == {"comm": "dd", "count": 5000}  # sorted desc
    assert {"bucket": "[4, 8)", "count": 42} in dist["latency_us"]

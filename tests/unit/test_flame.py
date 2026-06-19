"""Unit tests for the server's on-demand window flamegraph (continuous profiling)."""
import os
import tempfile

from app import flame


def _w(text: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".folded")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    return path


def test_merge_folded_files_sums_counts():
    a = _w("main;a 5\nmain;b 1\n")
    b = _w("main;a 3\nmain;c 4\n")
    merged = flame.merge_folded_files([a, b])
    os.remove(a)
    os.remove(b)
    assert merged == {"main;a": 8, "main;b": 1, "main;c": 4}


def test_missing_file_is_ignored():
    assert flame.merge_folded_files(["/no/such/file.folded"]) == {}


def test_build_tree_and_render():
    tree = flame.build_tree({"main;a": 8, "main;b": 1}, "window")
    assert tree["value"] == 9
    svg = flame.render_svg(tree, "t")
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "9 samples" in svg

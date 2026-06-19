"""Analyzer entrypoint: poll for finished tasks, turn raw data into a flamegraph + TopN.

Idempotency is enforced server-side (the /internal/analysis/next claim flips the task to
analysis RUNNING under a row lock), so a single-threaded poll loop is safe even if more
than one analyzer instance is running.
"""
import json
import logging
import os
import time

from .client import AnalyzerClient
from .config import Config
from .flamegraph import render_svg
from .logging_config import configure_logging
from .stacks import build_tree, compute_topn, parse_folded, parse_perf_script

logger = logging.getLogger("minidrop.analyzer")


class AnalysisError(Exception):
    pass


def _write(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def process_job(job: dict, cfg: Config) -> dict:
    tid = job["tid"]
    profiler = job.get("profiler_type", "")
    files = job.get("result_files") or {}
    out_dir = os.path.join(cfg.artifacts_dir, tid)

    if "perf_script" in files:
        folded = parse_perf_script(os.path.join(out_dir, files["perf_script"]))
        scheme = "hot"
    elif "pyspy_folded" in files:
        folded = parse_folded(os.path.join(out_dir, files["pyspy_folded"]))
        scheme = "python"
    else:
        raise AnalysisError(f"no known raw artifact in {list(files)}")

    if not folded:
        raise AnalysisError("no stacks parsed from raw data (empty or unrecognized format)")

    tree = build_tree(folded, root_name=f"{profiler} all")
    svg = render_svg(tree, title=f"{profiler} flamegraph (tid={tid})", scheme=scheme)
    top = compute_topn(folded, cfg.topn)

    _write(os.path.join(out_dir, "flamegraph.svg"), svg)
    _write(os.path.join(out_dir, "top.json"), json.dumps(top, ensure_ascii=False, indent=2))
    _write(os.path.join(out_dir, "tree.json"), json.dumps(tree, ensure_ascii=False))
    return {"flamegraph": "flamegraph.svg", "topn": "top.json", "tree": "tree.json"}


def main() -> None:
    configure_logging()
    cfg = Config()
    client = AnalyzerClient(cfg.server_url)
    logger.info("analyzer starting (server=%s, poll=%ss)", cfg.server_url, cfg.poll_interval_sec)

    while True:
        try:
            job = client.next_job()
        except Exception as exc:
            logger.warning("poll failed: %s", exc)
            time.sleep(cfg.poll_interval_sec)
            continue

        if not job:
            time.sleep(cfg.poll_interval_sec)
            continue

        tid = job["tid"]
        try:
            produced = process_job(job, cfg)
            client.report(tid, True, files=produced)
            logger.info("analyzed %s -> %s", tid, produced)
        except Exception as exc:
            logger.warning("analysis failed for %s: %s", tid, exc)
            try:
                client.report(tid, False, error=str(exc))
            except Exception as report_exc:
                logger.error("could not report failure for %s: %s", tid, report_exc)


if __name__ == "__main__":
    main()

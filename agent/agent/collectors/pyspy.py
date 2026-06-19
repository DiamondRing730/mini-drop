"""py-spy collector: Python language-level sampling, emitted as folded stacks.

Different stack-capture semantics from perf: py-spy walks the CPython interpreter frames,
so the stacks are Python function names (with native frames as <module>), giving a
language-level flamegraph that perf cannot produce.
"""
import os

from .base import Collector, CollectorError, run


class PySpyCollector(Collector):
    name = "pyspy"

    def collect(self, task: dict, out_dir: str) -> dict:
        pid = int(task["target_pid"])
        duration = int(task["duration_sec"])
        hz = int(task["frequency_hz"])

        if not os.path.isdir(f"/proc/{pid}"):
            raise CollectorError(f"target pid {pid} does not exist")

        folded = os.path.join(out_dir, "pyspy.folded")
        # --format raw emits collapsed/folded stacks directly (flamegraph-ready).
        rc, _out, err = run(
            ["py-spy", "record", "--format", "raw", "--rate", str(hz),
             "--duration", str(duration), "--pid", str(pid), "-o", folded],
            timeout=duration + 20,
        )
        if rc != 0 or not os.path.isfile(folded) or os.path.getsize(folded) == 0:
            raise CollectorError(f"py-spy failed (rc={rc}): {err[-400:]}")

        return {"pyspy_folded": "pyspy.folded"}

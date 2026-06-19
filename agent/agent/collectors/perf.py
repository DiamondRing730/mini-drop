"""perf CPU collector: record native stacks, then dump them as text for the analyzer."""
import os

from .base import Collector, CollectorError, run


class PerfCollector(Collector):
    name = "perf"

    def __init__(self, perf_event: str = "cpu-clock") -> None:
        # cpu-clock is a software event -> works under WSL2 where the hardware PMU is absent.
        self.perf_event = perf_event

    def collect(self, task: dict, out_dir: str) -> dict:
        pid = int(task["target_pid"])
        duration = int(task["duration_sec"])
        hz = int(task["frequency_hz"])

        if not os.path.isdir(f"/proc/{pid}"):
            raise CollectorError(f"target pid {pid} does not exist")

        perf_data = os.path.join(out_dir, "perf.data")
        rc, _out, err = run(
            ["perf", "record", "-e", self.perf_event, "-F", str(hz), "-g",
             "-o", perf_data, "-p", str(pid), "--", "sleep", str(duration)],
            timeout=duration + 20,
        )
        if rc != 0 or not os.path.isfile(perf_data):
            raise CollectorError(f"perf record failed (rc={rc}): {err[-400:]}")

        # Dump to text; the analyzer runs stackcollapse + flamegraph on this.
        script_txt = os.path.join(out_dir, "perf.script.txt")
        rc2, _o2, err2 = run(
            ["perf", "script", "-i", perf_data], timeout=120, stdout_path=script_txt
        )
        if rc2 != 0 or not os.path.isfile(script_txt) or os.path.getsize(script_txt) == 0:
            raise CollectorError(f"perf script failed (rc={rc2}): {err2[-400:]}")

        return {"perf_script": "perf.script.txt"}

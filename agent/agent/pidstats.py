"""Self-resource sampling from /proc.

Reports the agent's own CPU% / RSS / IO rate on each heartbeat, so the platform can prove
the collection probe is not itself hammering the host. Rates are computed as deltas between
consecutive samples (i.e. between heartbeats), so the first sample reports zeros.
"""
import os
import time

_CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100


def _read_cpu_ticks() -> int:
    with open("/proc/self/stat") as f:
        data = f.read()
    # comm (field 2) may contain spaces/parens; everything after the last ')' is unambiguous.
    after = data[data.rfind(")") + 2:].split()
    utime, stime = int(after[11]), int(after[12])  # fields 14,15
    return utime + stime


def _read_io() -> tuple[int, int]:
    read_bytes = write_bytes = 0
    try:
        with open("/proc/self/io") as f:
            for line in f:
                if line.startswith("read_bytes:"):
                    read_bytes = int(line.split()[1])
                elif line.startswith("write_bytes:"):
                    write_bytes = int(line.split()[1])
    except OSError:
        pass
    return read_bytes, write_bytes


def _read_rss_kb() -> int:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return 0


class PidStatsSampler:
    def __init__(self) -> None:
        self._prev: tuple[float, int, int, int] | None = None

    def sample(self) -> dict:
        """Return a self-resource snapshot. Safe to call on non-Linux (returns zeros)."""
        try:
            ts = time.monotonic()
            cpu = _read_cpu_ticks()
            rb, wb = _read_io()
            out = {
                "rss_kb": _read_rss_kb(),
                "num_threads": len(os.listdir("/proc/self/task")),
                "cpu_pct": 0.0,
                "io_read_kbps": 0.0,
                "io_write_kbps": 0.0,
            }
            if self._prev is not None:
                dt = ts - self._prev[0]
                if dt > 0:
                    out["cpu_pct"] = round((cpu - self._prev[1]) / _CLK_TCK / dt * 100, 2)
                    out["io_read_kbps"] = round((rb - self._prev[2]) / 1024 / dt, 2)
                    out["io_write_kbps"] = round((wb - self._prev[3]) / 1024 / dt, 2)
            self._prev = (ts, cpu, rb, wb)
            return out
        except (OSError, ValueError, IndexError):
            return {}

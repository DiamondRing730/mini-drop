"""eBPF collector via bpftrace: read/write syscall latency distribution.

Uses kernel tracepoints (sys_enter_read/write + sys_exit_read/write) to build a latency
histogram and a per-process breakdown. Chosen over raw block tracepoints because syscall
tracepoints fire reliably under WSL2 (where the block layer is virtualized), so a live
`dd`/`fio` visibly shifts the distribution.

No BEGIN probe (it fails to parse on the target bpftrace build); the run is bounded by an
`interval` probe that clears the scratch map and exits, so only the result maps are printed.
"""
import os

from .base import Collector, CollectorError, run

# %FILTER% -> "/pid == N/" (target a process) or "" (system-wide); %DUR% -> seconds.
_PROGRAM = r"""
tracepoint:syscalls:sys_enter_read,
tracepoint:syscalls:sys_enter_write
%FILTER%
{ @start[tid] = nsecs; }

tracepoint:syscalls:sys_exit_read,
tracepoint:syscalls:sys_exit_write
/@start[tid]/
{
  // guard against cross-CPU nsecs skew underflowing the unsigned subtraction
  if (nsecs > @start[tid]) {
    @usecs = hist((nsecs - @start[tid]) / 1000);
    @by_comm[comm] = count();
  }
  delete(@start[tid]);
}

interval:s:%DUR% { clear(@start); exit(); }
"""


class EbpfCollector(Collector):
    name = "ebpf"

    def collect(self, task: dict, out_dir: str) -> dict:
        duration = int(task["duration_sec"])
        pid = int(task["target_pid"])
        # pid <= 0 -> system-wide (classic eBPF distribution view).
        filt = f"/pid == {pid}/" if pid > 0 else ""
        program = _PROGRAM.replace("%FILTER%", filt).replace("%DUR%", str(duration))

        out = os.path.join(out_dir, "ebpf.txt")
        rc, _out, err = run(["bpftrace", "-e", program], timeout=duration + 25, stdout_path=out)
        if rc != 0 or not os.path.isfile(out) or os.path.getsize(out) == 0:
            raise CollectorError(f"bpftrace failed (rc={rc}): {err[-500:]}")
        return {"ebpf_hist": "ebpf.txt"}

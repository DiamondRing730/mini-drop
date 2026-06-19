"""Parse bpftrace output into a chartable JSON distribution.

bpftrace prints log2 histograms like:

    @usecs:
    [0]                  3 |@@@                                |
    [2, 4)               7 |@@@@@@@                            |
    [4, 8)              42 |@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@|

and per-key counts like:

    @by_comm[dd]: 5000
"""
import re

_BUCKET = re.compile(r"^(\[[^\]\)]*[\]\)])\s+(\d+)")
_BY_COMM = re.compile(r"^@by_comm\[(.+)\]:\s+(\d+)")


def parse_bpftrace(path: str) -> dict:
    latency: list[dict] = []
    by_comm: list[dict] = []
    with open(path, errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            m = _BY_COMM.match(line)
            if m:
                by_comm.append({"comm": m.group(1), "count": int(m.group(2))})
                continue
            m = _BUCKET.match(line)
            if m:
                latency.append({"bucket": m.group(1), "count": int(m.group(2))})

    by_comm.sort(key=lambda x: -x["count"])
    total = sum(b["count"] for b in latency)
    return {
        "kind": "ebpf-syscall-latency",
        "unit": "microseconds",
        "total_events": total,
        "latency_us": latency,
        "by_comm": by_comm[:20],
    }

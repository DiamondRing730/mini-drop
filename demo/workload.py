"""Selectable demo workloads for independent Mini-Drop profiling tasks."""
import argparse
import functools
import math
import os
import tempfile
import time


parser = argparse.ArgumentParser()
parser.add_argument(
    "--scenario",
    choices=["cpu-before", "cpu-after", "numeric", "io"],
    default=os.environ.get("DEMO_SCENARIO", "cpu-before"),
)
SCENARIO = parser.parse_args().scenario


if SCENARIO == "cpu-after":
    @functools.lru_cache(maxsize=None)
    def fib(n: int) -> int:
        """Optimized version: every Fibonacci subproblem is computed once."""
        return n if n < 2 else fib(n - 1) + fib(n - 2)
else:
    def fib(n: int) -> int:
        """Baseline version: intentionally repeats the same recursive work."""
        return n if n < 2 else fib(n - 1) + fib(n - 2)


def crunch_numbers() -> float:
    total = 0.0
    for i in range(1, 20000):
        total += math.sqrt(i) * math.sin(i)
    return total


def hot_path() -> float:
    return fib(28) + crunch_numbers()


def warm_path() -> int:
    total = 0
    for i in range(200000):
        total += i * i
    return total


def cpu_service() -> float:
    """Identical call structure for before/after; only fib implementation changes."""
    return hot_path() + warm_path()


def polynomial_loop() -> int:
    total = 0
    for i in range(450000):
        total += (i * i + 3 * i + 7) % 1009
    return total


def trigonometry_loop() -> float:
    total = 0.0
    for i in range(1, 160000):
        total += math.sin(i / 10.0) * math.cos(i / 17.0)
    return total


def numeric_service() -> float:
    return polynomial_loop() + trigonometry_loop()


def io_service(path: str, block: bytes) -> int:
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        written = os.write(fd, block)
        os.lseek(fd, 0, os.SEEK_SET)
        read_back = len(os.read(fd, len(block)))
        return written + read_back
    finally:
        os.close(fd)


def main() -> None:
    print(f"workload started: scenario={SCENARIO}", flush=True)
    iterations = 0
    started = time.monotonic()
    io_path = os.path.join(tempfile.gettempdir(), "minidrop-demo-io.bin")
    io_block = b"minidrop" * 8192
    while True:
        if SCENARIO in {"cpu-before", "cpu-after"}:
            cpu_service()
        elif SCENARIO == "numeric":
            numeric_service()
        else:
            io_service(io_path, io_block)
            time.sleep(0.001)
        iterations += 1
        if iterations % 100 == 0:
            elapsed = max(time.monotonic() - started, 0.001)
            print(f"scenario={SCENARIO} iterations={iterations} rate={iterations / elapsed:.1f}/s", flush=True)


if __name__ == "__main__":
    main()

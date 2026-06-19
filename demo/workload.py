"""A deterministic CPU-bound workload with clearly named nested frames.

Used by `make demo` as the profiling target so the flamegraph shows a recognizable shape:
service -> hot_path -> {fib, crunch_numbers} and service -> warm_path.
"""
import math
import time


def fib(n: int) -> int:
    return n if n < 2 else fib(n - 1) + fib(n - 2)


def crunch_numbers() -> float:
    total = 0.0
    for i in range(1, 20000):
        total += math.sqrt(i) * math.sin(i)
    return total


def hot_path() -> float:
    return fib(28) + crunch_numbers()


def warm_path() -> int:
    s = 0
    for i in range(200000):
        s += i * i
    return s


def service() -> float:
    return hot_path() + warm_path()


def main() -> None:
    print("workload started", flush=True)
    while True:
        service()
        time.sleep(0.001)


if __name__ == "__main__":
    main()

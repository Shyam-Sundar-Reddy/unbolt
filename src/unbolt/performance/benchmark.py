"""run_benchmarks: controlled, reproducible timing, always labeled
"measured" (goal.md section 4/12 - never mixed with an estimate).
stdlib time.perf_counter + statistics; see docs/decisions for why this
isn't pytest-benchmark.
"""

import platform
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    label: str
    name: str
    rounds: int
    mean_seconds: float
    stdev_seconds: float
    min_seconds: float
    max_seconds: float
    environment: dict[str, str]


def _environment() -> dict[str, str]:
    return {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
    }


def run_benchmarks(
    name: str, fn: Callable[[], object], *, rounds: int = 10, warmup_rounds: int = 2
) -> BenchmarkResult:
    """Times `fn` `rounds` times after `warmup_rounds` untimed calls.

    Records the environment alongside the timing - a number without its
    environment isn't reproducible, just a stray fact.
    """
    for _ in range(warmup_rounds):
        fn()

    timings = []
    for _ in range(rounds):
        start = time.perf_counter()
        fn()
        timings.append(time.perf_counter() - start)

    return BenchmarkResult(
        label="measured",
        name=name,
        rounds=rounds,
        mean_seconds=statistics.mean(timings),
        stdev_seconds=statistics.stdev(timings) if rounds > 1 else 0.0,
        min_seconds=min(timings),
        max_seconds=max(timings),
        environment=_environment(),
    )

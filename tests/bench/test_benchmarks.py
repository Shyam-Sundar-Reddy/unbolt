"""Correctness tests for the benchmark harness itself - kept fast (small
field counts) so routine test runs stay quick. The real measured
numbers at realistic field counts come from tools/gen_performance_doc.py,
run separately, not from every CI invocation of the test suite.
"""

from tests.bench.synthetic import synthetic_copybook
from unbolt.dsl import build_dsl
from unbolt.parser import parse_copybook
from unbolt.performance import run_benchmarks


def test_result_is_labeled_measured() -> None:
    result = run_benchmarks("noop", lambda: None, rounds=3, warmup_rounds=1)
    assert result.label == "measured"


def test_rounds_and_timings_are_consistent() -> None:
    result = run_benchmarks("noop", lambda: None, rounds=5, warmup_rounds=1)
    assert result.rounds == 5
    assert result.min_seconds <= result.mean_seconds <= result.max_seconds
    assert result.mean_seconds >= 0


def test_environment_is_recorded() -> None:
    result = run_benchmarks("noop", lambda: None, rounds=1, warmup_rounds=0)
    assert "python_version" in result.environment
    assert "platform" in result.environment


def test_single_round_has_zero_stdev_not_a_crash() -> None:
    result = run_benchmarks("noop", lambda: None, rounds=1, warmup_rounds=0)
    assert result.stdev_seconds == 0.0


def test_benchmarking_parse_on_a_small_synthetic_copybook() -> None:
    source = synthetic_copybook(10)
    result = run_benchmarks("parse-10", lambda: parse_copybook(source), rounds=3, warmup_rounds=1)
    assert result.label == "measured"


def test_benchmarking_build_dsl_on_a_small_synthetic_copybook() -> None:
    source = synthetic_copybook(10)
    parsed = parse_copybook(source)
    result = run_benchmarks(
        "build_dsl-10",
        lambda: build_dsl(parsed, source_file="bench.cpy"),
        rounds=3,
        warmup_rounds=1,
    )
    assert result.label == "measured"

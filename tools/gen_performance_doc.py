"""Run the real measurements and write docs/performance.md.

Not part of CI or the routine test suite (tests/bench/test_benchmarks.py
keeps small, fast correctness checks instead) - this is the dev-time
script that produces the actual numbers docs/performance.md reports,
run manually when those numbers need refreshing.
"""

import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from tests.bench.synthetic import synthetic_copybook  # noqa: E402
from unbolt.dsl import build_dsl  # noqa: E402
from unbolt.exceptions import UnapprovedMappingError  # noqa: E402
from unbolt.generators import generate_code  # noqa: E402
from unbolt.mapping import recommend_mappings  # noqa: E402
from unbolt.parser import parse_copybook  # noqa: E402
from unbolt.performance import estimate_storage, run_benchmarks  # noqa: E402

FIXTURES_DIR = ROOT / "fixtures"
FIELD_COUNTS = (100, 1_000, 10_000)


def _measure_pipeline(field_count: int) -> list[tuple[str, object]]:
    source = synthetic_copybook(field_count)
    results = []

    parse_result = run_benchmarks(f"parse-{field_count}", lambda: parse_copybook(source))
    results.append((f"parse ({field_count} fields)", parse_result))

    parsed = parse_copybook(source)
    build_result = run_benchmarks(
        f"build_dsl-{field_count}", lambda: build_dsl(parsed, source_file="bench.cpy")
    )
    results.append((f"build_dsl ({field_count} fields)", build_result))

    dsl = build_dsl(parsed, source_file="bench.cpy")
    map_result = run_benchmarks(f"recommend-{field_count}", lambda: recommend_mappings(dsl, "go"))
    results.append((f"recommend_mappings, go ({field_count} fields)", map_result))

    mapping = recommend_mappings(dsl, "go")
    gen_result = run_benchmarks(
        f"generate-{field_count}", lambda: generate_code(dsl, mapping, "go")
    )
    results.append((f"generate_code, go ({field_count} fields)", gen_result))

    return results


def _estimates_section() -> str:
    lines = ["## Estimated: real fixtures", ""]
    lines.append("| Fixture | COBOL bytes | Go bytes |")
    lines.append("|---|---|---|")
    for fixture in sorted(FIXTURES_DIR.glob("*.cpy")):
        source = fixture.read_text()
        dsl = build_dsl(parse_copybook(source), source_file=fixture.name)
        mapping = recommend_mappings(dsl, "go")
        try:
            (est,) = estimate_storage(dsl, mapping)
        except UnapprovedMappingError:
            continue  # mixed_usage needs overrides for COMP-1/2; skip here
        target = est.target_record_bytes if est.target_record_bytes is not None else "variable"
        lines.append(f"| `{fixture.name}` | {est.cobol_record_bytes} | {target} |")
    return "\n".join(lines)


def main() -> None:
    all_results = []
    for count in FIELD_COUNTS:
        all_results.extend(_measure_pipeline(count))

    env = all_results[0][1].environment
    today = datetime.date.today().isoformat()

    lines = [
        "# Performance",
        "",
        "Estimated and measured numbers are never mixed - goal.md "
        "section 4/12. An estimate is arithmetic from byte sizes "
        "already computed in Phase 1; a measurement is a real timed "
        "run, with its environment recorded alongside it.",
        "",
        f"## Measured: pipeline stage timings (dated {today})",
        "",
        f"Environment: Python {env['python_version']}, {env['platform']}, "
        f"{env['processor']}.",
        "",
        "| Stage | Rounds | Mean | Stdev | Min | Max |",
        "|---|---|---|---|---|---|",
    ]
    for name, result in all_results:
        lines.append(
            f"| {name} | {result.rounds} | {result.mean_seconds * 1000:.2f} ms "
            f"| {result.stdev_seconds * 1000:.2f} ms | {result.min_seconds * 1000:.2f} ms "
            f"| {result.max_seconds * 1000:.2f} ms |"
        )

    lines.append("")
    lines.append(_estimates_section())
    lines.append("")
    lines.append(
        "## CI regression budget\n\n"
        "Not wired into CI yet: goal.md section 4 says to set the "
        "budget from the first real measurement, not a guess - the "
        "table above *is* that first measurement, recorded "
        f"{today}. A regression check needs a prior run to compare "
        "against, which doesn't exist until this has been measured "
        "again at least once. Revisit once there's a second data point."
    )

    out_path = ROOT / "docs" / "performance.md"
    out_path.write_text("\n".join(lines) + "\n")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()

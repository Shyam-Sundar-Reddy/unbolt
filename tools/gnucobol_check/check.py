"""Cross-check unbolt's byte-size math against a real compiler.

Not part of CI and not a replacement for the IBM-Enterprise-based golden
tests in tests/ - GnuCOBOL is a different dialect (decision 0001 keeps
IBM Enterprise as the documented target) and this script only checks
LENGTH OF, not EBCDIC content or TRUNC(STD) range semantics. What it DOES
give us: an independent compiler's opinion on every field's byte size,
including the trickiest case (REDEFINES group sizing), computed without
reading a single line of our own sizing.py.

Usage: uv run python tools/gnucobol_check/check.py
Requires: `docker build -t unbolt-gnucobol-check tools/gnucobol_check`
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from unbolt.dsl import Dsl, FieldNode, build_dsl  # noqa: E402
from unbolt.parser import parse_copybook  # noqa: E402

FIXTURES_DIR = ROOT / "tests" / "fixtures"
IMAGE = "unbolt-gnucobol-check"


def _collect_expected(dsl: Dsl) -> dict[str, int]:
    expected: dict[str, int] = {}

    def walk(node: FieldNode) -> None:
        expected[node.name] = node.byte_size
        for child in node.children:
            walk(child)

    for root in dsl.roots:
        walk(root)
    return expected


def _wrapper_source(fixture_name: str, field_names: list[str]) -> str:
    lines = [
        "       IDENTIFICATION DIVISION.",
        "       PROGRAM-ID. CHECK-LENGTHS.",
        "       DATA DIVISION.",
        "       WORKING-STORAGE SECTION.",
        f'       COPY "{fixture_name}".',
        "       PROCEDURE DIVISION.",
    ]
    for name in field_names:
        lines.append(f'           DISPLAY "{name}=" LENGTH OF {name}.')
    lines.append("           STOP RUN.")
    return "\n".join(lines) + "\n"


def _run_in_docker(fixture_path: Path, wrapper_path: Path) -> str:
    result = subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{fixture_path.parent}:/copybooks:ro",
            "-v", f"{wrapper_path.parent}:/work",
            "-w", "/work",
            IMAGE,
            "sh", "-c",
            f"cobc -x -I /copybooks {wrapper_path.name} -o a.out && ./a.out",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"GnuCOBOL failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout


def main() -> int:
    ok = True
    for fixture in sorted(FIXTURES_DIR.glob("*.cpy")):
        source = fixture.read_text()
        dsl = build_dsl(parse_copybook(source), source_file=fixture.name)
        expected = _collect_expected(dsl)

        wrapper_path = fixture.with_suffix(".check.cbl")
        wrapper_path.write_text(_wrapper_source(fixture.name, list(expected)))
        try:
            output = _run_in_docker(fixture, wrapper_path)
        finally:
            wrapper_path.unlink(missing_ok=True)
            (wrapper_path.parent / "a.out").unlink(missing_ok=True)

        actual = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)

        print(f"== {fixture.name} ==")
        for name, expected_size in expected.items():
            gnucobol_size = int(actual.get(name, -1))
            status = "OK" if gnucobol_size == expected_size else "MISMATCH"
            if status == "MISMATCH":
                ok = False
            print(f"  {status:8} {name}: unbolt={expected_size} gnucobol={gnucobol_size}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

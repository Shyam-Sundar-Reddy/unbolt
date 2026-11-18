"""Compile-check generated Go and Java against every sample copybook.

Phase 3 step 8 (docs/phase.md): "if Go/Java toolchains are present
locally, compile-check generated output." Uses Docker instead of
requiring a local Go/Java install - skips gracefully (prints why, exits
0) if Docker isn't available. Not wired into CI; a dev-time check.

Usage: uv run python tools/compile_check/check.py
"""

import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from unbolt.dsl import build_dsl  # noqa: E402
from unbolt.generators.go import generate_go  # noqa: E402
from unbolt.generators.go_decoder import generate_go_decoder  # noqa: E402
from unbolt.generators.java import generate_java  # noqa: E402
from unbolt.generators.resolve import resolve_mapping  # noqa: E402
from unbolt.mapping import recommend_mappings  # noqa: E402
from unbolt.overrides import Overrides, apply_override  # noqa: E402
from unbolt.parser import parse_copybook  # noqa: E402

FIXTURES_DIR = ROOT / "fixtures"

# Same bytes and expected values as
# tests/test_decoding_record.py::test_flat_display_record_decodes_every_field_exactly -
# this is a real round-trip check (ADR 0009: "not optional"), not just a compile check:
# the generated Go must decode to the exact values Python's own decoder already verified.
_FLAT_DISPLAY_GO_MAIN = """package main

import "fmt"

func main() {
	data := []byte{
		0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6,
		0xF0, 0xF4, 0xD5,
		0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xC9,
	}
	r, err := NewCustomerRecord(data)
	if err != nil {
		panic(err)
	}
	id, err := r.CustomerId()
	if err != nil || id != 123456 {
		panic(fmt.Sprintf("CustomerId: got (%v, %v), want (123456, nil)", id, err))
	}
	age, err := r.CustomerAge()
	if err != nil || age != -45 {
		panic(fmt.Sprintf("CustomerAge: got (%v, %v), want (-45, nil)", age, err))
	}
	bal, err := r.AccountBalance()
	if err != nil || bal != 123456789 {
		panic(fmt.Sprintf("AccountBalance: got (%v, %v), want (123456789, nil)", bal, err))
	}
	fmt.Println("flat_display Go decoder round-trip: OK")
}
"""


def _overrides_for(name: str) -> Overrides:
    if name != "mixed_usage":
        return Overrides()
    overrides = apply_override(
        Overrides(),
        "FINANCIAL-RECORD.SENSOR-READING",
        "float32",
        "best-effort IEEE754 approximation (goal.md §5.4)",
        valid_choices=[],
        force=True,
    )
    return apply_override(
        overrides,
        "FINANCIAL-RECORD.PRECISE-READING",
        "float64",
        "best-effort IEEE754 approximation (goal.md §5.4)",
        valid_choices=[],
        force=True,
    )


def _java_overrides_for(name: str) -> Overrides:
    if name != "mixed_usage":
        return Overrides()
    overrides = apply_override(
        Overrides(),
        "FINANCIAL-RECORD.SENSOR-READING",
        "float",
        "best-effort IEEE754 approximation (goal.md §5.4)",
        valid_choices=[],
        force=True,
    )
    return apply_override(
        overrides,
        "FINANCIAL-RECORD.PRECISE-READING",
        "double",
        "best-effort IEEE754 approximation (goal.md §5.4)",
        valid_choices=[],
        force=True,
    )


def _run_docker(image: str, work_dir: pathlib.Path, command: str) -> tuple[bool, str]:
    args = [
        "docker", "run", "--rm",
        "-v", f"{work_dir}:/work",
        "-w", "/work",
        image, "sh", "-c", command,
    ]
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    return result.returncode == 0, result.stdout + result.stderr


def main() -> int:
    if shutil.which("docker") is None:
        print("Docker not found - skipping compile-check.")
        return 0

    out_dir = ROOT / ".compile_check_tmp"
    go_dir = out_dir / "go"
    java_dir = out_dir / "java"
    go_decoder_dir = out_dir / "go_decoder"
    go_dir.mkdir(parents=True, exist_ok=True)
    java_dir.mkdir(parents=True, exist_ok=True)
    go_decoder_dir.mkdir(parents=True, exist_ok=True)

    ok = True
    for fixture in sorted(FIXTURES_DIR.glob("*.cpy")):
        name = fixture.stem
        source = fixture.read_text()
        dsl = build_dsl(parse_copybook(source), source_file=fixture.name)

        go_report = recommend_mappings(dsl, "go")
        go_resolved = resolve_mapping(go_report, _overrides_for(name))
        go_sub = go_dir / name
        go_sub.mkdir(exist_ok=True)
        (go_sub / "gen.go").write_text(generate_go(dsl, go_resolved))

        java_report = recommend_mappings(dsl, "java")
        java_resolved = resolve_mapping(java_report, _java_overrides_for(name))
        java_sub = java_dir / name
        java_sub.mkdir(exist_ok=True)
        for class_name, src in generate_java(dsl, java_resolved).items():
            (java_sub / f"{class_name}.java").write_text(src)

    go_passed, go_output = _run_docker(
        "golang:1.23",
        go_dir,
        "for d in */; do (cd \"$d\" && go mod init tmp >/dev/null 2>&1 && go build .) "
        '|| { echo "FAILED: $d"; exit 1; }; done',
    )
    print("Go:", "OK" if go_passed else f"FAILED\n{go_output}")
    ok = ok and go_passed

    java_passed, java_output = _run_docker(
        "eclipse-temurin:21-jdk",
        java_dir,
        'for d in */; do (cd "$d" && javac *.java) || { echo "FAILED: $d"; exit 1; }; done',
    )
    print("Java:", "OK" if java_passed else f"FAILED\n{java_output}")
    ok = ok and java_passed

    # Go flyweight decoder (ADR 0009, Phase 10): flat_display.cpy is the
    # only fixture inside this slice's current scope (flat, DISPLAY-only
    # records) - a real round-trip check, not just compile: the running
    # binary must decode to the exact values Python's own decoder gives.
    flat_source = (FIXTURES_DIR / "flat_display.cpy").read_text()
    flat_dsl = build_dsl(parse_copybook(flat_source), source_file="flat_display.cpy")
    flat_resolved = resolve_mapping(recommend_mappings(flat_dsl, "go"), Overrides())
    decoder_src = generate_go_decoder(flat_dsl, flat_resolved).replace(
        "package generated", "package main", 1
    )
    (go_decoder_dir / "gen_decoder.go").write_text(decoder_src)
    (go_decoder_dir / "main.go").write_text(_FLAT_DISPLAY_GO_MAIN)
    decoder_passed, decoder_output = _run_docker(
        "golang:1.23",
        go_decoder_dir,
        "go mod init tmp >/dev/null 2>&1 && go run .",
    )
    print("Go decoder round-trip:", "OK" if decoder_passed else f"FAILED\n{decoder_output}")
    if decoder_passed:
        print(decoder_output.strip())
    ok = ok and decoder_passed

    shutil.rmtree(out_dir)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

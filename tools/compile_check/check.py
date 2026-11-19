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

# No existing fixture exercises DISPLAY+COMP-3+binary together within
# the decoder's current slice (mixed_usage.cpy also has COMP-1/COMP-2,
# which the decoder doesn't support yet) - a small synthetic copybook,
# not tied to any fixture file, covering the three usages this slice
# does support in one record. Bytes and expected values hand-computed
# and cross-checked against decode_record() directly before writing
# them here (never guessed).
_PACKED_BINARY_SOURCE = """01 REC.
    05 UNSIGNED-DISPLAY PIC 9(6).
    05 SIGNED-DISPLAY PIC S9(3).
    05 PACKED PIC S9(9) COMP-3.
    05 BINARY PIC S9(9) COMP.
"""

_PACKED_BINARY_GO_MAIN = """package main

import "fmt"

func main() {
	data := []byte{
		0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, // UNSIGNED-DISPLAY "123456"
		0xF1, 0xF2, 0xD3, // SIGNED-DISPLAY -123
		0x12, 0x34, 0x56, 0x78, 0x9D, // PACKED -123456789 (COMP-3)
		0xC5, 0x21, 0x97, 0x4F, // BINARY -987654321 (big-endian two's complement)
	}
	r, err := NewRec(data)
	if err != nil {
		panic(err)
	}
	if v, err := r.UnsignedDisplay(); err != nil || v != 123456 {
		panic(fmt.Sprintf("UnsignedDisplay: got (%v, %v), want (123456, nil)", v, err))
	}
	if v, err := r.SignedDisplay(); err != nil || v != -123 {
		panic(fmt.Sprintf("SignedDisplay: got (%v, %v), want (-123, nil)", v, err))
	}
	if v, err := r.Packed(); err != nil || v != -123456789 {
		panic(fmt.Sprintf("Packed: got (%v, %v), want (-123456789, nil)", v, err))
	}
	if v, err := r.Binary(); err != nil || v != -987654321 {
		panic(fmt.Sprintf("Binary: got (%v, %v), want (-987654321, nil)", v, err))
	}
	fmt.Println("COMP-3/binary Go decoder round-trip: OK")
}
"""

# nested_groups.cpy - a real fixture, now fully supported by this
# slice's nested-group support. Bytes and expected values hand-computed
# and cross-checked against decode_record() directly before writing
# them here (never guessed).
_NESTED_GROUPS_GO_MAIN = """package main

import "fmt"

func main() {
	data := []byte{
		0xF0, 0xF0, 0xF0, 0xF0, 0xF0, 0xF0, 0xF4, 0xF2, // ORDER-ID 42
		0xF2, 0xF0, 0xF2, 0xF4, // ORDER-YEAR 2024
		0xF1, 0xF1, // ORDER-MONTH 11
		0xF0, 0xF5, // ORDER-DAY 5
		0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xD9, // ORDER-TOTAL -123456789 unscaled
	}
	r, err := NewOrderRecord(data)
	if err != nil {
		panic(err)
	}
	header := r.OrderHeader()
	if v, err := header.OrderId(); err != nil || v != 42 {
		panic(fmt.Sprintf("OrderId: got (%v, %v), want (42, nil)", v, err))
	}
	date := header.OrderDate()
	if v, err := date.OrderYear(); err != nil || v != 2024 {
		panic(fmt.Sprintf("OrderYear: got (%v, %v), want (2024, nil)", v, err))
	}
	if v, err := date.OrderMonth(); err != nil || v != 11 {
		panic(fmt.Sprintf("OrderMonth: got (%v, %v), want (11, nil)", v, err))
	}
	if v, err := date.OrderDay(); err != nil || v != 5 {
		panic(fmt.Sprintf("OrderDay: got (%v, %v), want (5, nil)", v, err))
	}
	if v, err := r.OrderTotal(); err != nil || v != -123456789 {
		panic(fmt.Sprintf("OrderTotal: got (%v, %v), want (-123456789, nil)", v, err))
	}
	fmt.Println("nested_groups Go decoder round-trip: OK")
}
"""

# All three sign placements the decoder doesn't default to (trailing
# overpunch, covered by flat_display.cpy already): leading overpunch,
# trailing separate, leading separate. No fixture uses SIGN - a small
# synthetic copybook, bytes hand-computed and cross-checked against
# decode_record() directly before writing them here.
_SIGN_PLACEMENTS_SOURCE = """01 REC.
    05 LEAD-OVP PIC S9(3) SIGN IS LEADING.
    05 TRAIL-SEP PIC S9(3) SIGN IS SEPARATE.
    05 LEAD-SEP PIC S9(3) SIGN IS LEADING SEPARATE.
"""

_SIGN_PLACEMENTS_GO_MAIN = """package main

import "fmt"

func main() {
	data := []byte{
		0xD1, 0xF2, 0xF3, // LEAD-OVP -123 (leading overpunch)
		0xF4, 0xF5, 0xF6, 0x60, // TRAIL-SEP -456 (trailing separate)
		0x60, 0xF7, 0xF8, 0xF9, // LEAD-SEP -789 (leading separate)
	}
	r, err := NewRec(data)
	if err != nil {
		panic(err)
	}
	if v, err := r.LeadOvp(); err != nil || v != -123 {
		panic(fmt.Sprintf("LeadOvp: got (%v, %v), want (-123, nil)", v, err))
	}
	if v, err := r.TrailSep(); err != nil || v != -456 {
		panic(fmt.Sprintf("TrailSep: got (%v, %v), want (-456, nil)", v, err))
	}
	if v, err := r.LeadSep(); err != nil || v != -789 {
		panic(fmt.Sprintf("LeadSep: got (%v, %v), want (-789, nil)", v, err))
	}
	fmt.Println("sign placements Go decoder round-trip: OK")
}
"""


# big.Int (Phase 10, fifth slice): one field per supported usage/sign
# placement, each with a digit count that genuinely exceeds int64/
# uint64 range (20 digits unsigned, 19 signed - S9(19)'s magnitude
# exceeds int64's but still fits in 19 digits, so the ladder has to
# pick big.Int, not just int64). No fixture has a field this wide - a
# synthetic copybook, bytes hand-computed and cross-checked against
# decode_record() directly before writing them here.
_BIGINT_SOURCE = """01 REC.
    05 UNSIGNED-BIG PIC 9(20).
    05 TRAILING-OVP-BIG PIC S9(19).
    05 LEADING-OVP-BIG PIC S9(19) SIGN IS LEADING.
    05 TRAILING-SEP-BIG PIC S9(19) SIGN IS SEPARATE.
    05 LEADING-SEP-BIG PIC S9(19) SIGN IS LEADING SEPARATE.
    05 PACKED-BIG PIC S9(19) COMP-3.
"""

_BIGINT_GO_MAIN = """package main

import (
	"fmt"
	"math/big"
)

func main() {
	data := []byte{
		// UNSIGNED-BIG 12345678901234567890 (20 bytes)
		0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xF0,
		0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xF0,
		// TRAILING-OVP-BIG -1234567890123456789 (19 bytes)
		0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xF0,
		0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xD9,
		// LEADING-OVP-BIG -9876543210987654321 (19 bytes)
		0xD9, 0xF8, 0xF7, 0xF6, 0xF5, 0xF4, 0xF3, 0xF2, 0xF1, 0xF0,
		0xF9, 0xF8, 0xF7, 0xF6, 0xF5, 0xF4, 0xF3, 0xF2, 0xF1,
		// TRAILING-SEP-BIG +1111111111111111111 (20 bytes)
		0xF1, 0xF1, 0xF1, 0xF1, 0xF1, 0xF1, 0xF1, 0xF1, 0xF1, 0xF1,
		0xF1, 0xF1, 0xF1, 0xF1, 0xF1, 0xF1, 0xF1, 0xF1, 0xF1, 0x4E,
		// LEADING-SEP-BIG -2222222222222222222 (20 bytes)
		0x60, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2,
		0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2, 0xF2,
		// PACKED-BIG +9999999999999999999 (10 bytes)
		0x99, 0x99, 0x99, 0x99, 0x99, 0x99, 0x99, 0x99, 0x99, 0x9C,
	}
	r, err := NewRec(data)
	if err != nil {
		panic(err)
	}
	cases := []struct {
		name string
		get  func() (*big.Int, error)
		want string
	}{
		{"UnsignedBig", r.UnsignedBig, "12345678901234567890"},
		{"TrailingOvpBig", r.TrailingOvpBig, "-1234567890123456789"},
		{"LeadingOvpBig", r.LeadingOvpBig, "-9876543210987654321"},
		{"TrailingSepBig", r.TrailingSepBig, "1111111111111111111"},
		{"LeadingSepBig", r.LeadingSepBig, "-2222222222222222222"},
		{"PackedBig", r.PackedBig, "9999999999999999999"},
	}
	for _, c := range cases {
		v, err := c.get()
		if err != nil || v.String() != c.want {
			panic(fmt.Sprintf("%s: got (%v, %v), want (%s, nil)", c.name, v, err, c.want))
		}
	}
	fmt.Println("big.Int Go decoder round-trip: OK")
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


def _check_go_decoder_roundtrip(
    out_dir: pathlib.Path, label: str, source: str, go_main: str
) -> bool:
    dsl = build_dsl(parse_copybook(source), source_file=f"{label}.cpy")
    resolved = resolve_mapping(recommend_mappings(dsl, "go"), Overrides())
    decoder_src = generate_go_decoder(dsl, resolved).replace("package generated", "package main", 1)

    work_dir = out_dir / f"go_decoder_{label}"
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "gen_decoder.go").write_text(decoder_src)
    (work_dir / "main.go").write_text(go_main)

    passed, output = _run_docker(
        "golang:1.23", work_dir, "go mod init tmp >/dev/null 2>&1 && go run ."
    )
    print(f"Go decoder round-trip ({label}):", "OK" if passed else f"FAILED\n{output}")
    if passed:
        print(output.strip())
    return passed


def main() -> int:
    if shutil.which("docker") is None:
        print("Docker not found - skipping compile-check.")
        return 0

    out_dir = ROOT / ".compile_check_tmp"
    go_dir = out_dir / "go"
    java_dir = out_dir / "java"
    go_dir.mkdir(parents=True, exist_ok=True)
    java_dir.mkdir(parents=True, exist_ok=True)

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

    # Go flyweight decoder (ADR 0009, Phase 10): real round-trip checks,
    # not just compiles - the running binary must decode to the exact
    # values Python's own decode_record() already verified. Five cases:
    # flat_display.cpy (DISPLAY only), a synthetic DISPLAY+COMP-3+binary
    # record (no existing fixture combines those three within this
    # slice's scope, since mixed_usage.cpy also has COMP-1/COMP-2, which
    # isn't supported yet), nested_groups.cpy (nested group structs), a
    # synthetic record covering all three non-default sign placements
    # (no fixture uses SIGN at all), and a synthetic record covering
    # big.Int across every supported usage/sign placement (no fixture
    # has a field wide enough to need it).
    ok = ok and _check_go_decoder_roundtrip(
        out_dir, "flat_display", (FIXTURES_DIR / "flat_display.cpy").read_text(),
        _FLAT_DISPLAY_GO_MAIN,
    )
    ok = ok and _check_go_decoder_roundtrip(
        out_dir, "packed_binary", _PACKED_BINARY_SOURCE, _PACKED_BINARY_GO_MAIN
    )
    ok = ok and _check_go_decoder_roundtrip(
        out_dir, "nested_groups", (FIXTURES_DIR / "nested_groups.cpy").read_text(),
        _NESTED_GROUPS_GO_MAIN,
    )
    ok = ok and _check_go_decoder_roundtrip(
        out_dir, "sign_placements", _SIGN_PLACEMENTS_SOURCE, _SIGN_PLACEMENTS_GO_MAIN
    )
    ok = ok and _check_go_decoder_roundtrip(
        out_dir, "bigint", _BIGINT_SOURCE, _BIGINT_GO_MAIN
    )

    shutil.rmtree(out_dir)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

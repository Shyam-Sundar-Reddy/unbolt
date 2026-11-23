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
from unbolt.generators.go_decoder import (  # noqa: E402
    RedefinesDispatch,
    RedefinesRule,
    generate_go_decoder,
)
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


# Alphanumeric decode (Phase 10, sixth slice): a mix of letters,
# digits-as-text, and trailing-space padding, to exercise the cp037
# lookup table across more than just the identity-looking ASCII range.
# No fixture has a plain PIC X/A field within this slice's scope - a
# synthetic copybook, bytes hand-computed (via Python's own cp037
# codec) and cross-checked against decode_record() directly before
# writing them here.
_ALPHA_SOURCE = """01 REC.
    05 NAME PIC X(10).
    05 CODE PIC X(3).
"""

_ALPHA_GO_MAIN = """package main

import "fmt"

func main() {
	data := []byte{
		0xC8, 0xC5, 0xD3, 0xD3, 0xD6, 0x40, 0x40, 0x40, 0x40, 0x40, // NAME "HELLO     "
		0xC1, 0xC2, 0xF1, // CODE "AB1"
	}
	r, err := NewRec(data)
	if err != nil {
		panic(err)
	}
	if v := r.Name(); v != "HELLO     " {
		panic(fmt.Sprintf("Name: got %q, want %q", v, "HELLO     "))
	}
	if v := r.Code(); v != "AB1" {
		panic(fmt.Sprintf("Code: got %q, want %q", v, "AB1"))
	}
	fmt.Println("alphanumeric Go decoder round-trip: OK")
}
"""


# OCCURS (Phase 10, seventh slice): the real occurs_table.cpy fixture -
# a leaf OCCURS count field's sibling group, OCCURS 5 TIMES, each
# occurrence itself a group with an alphanumeric and a DISPLAY field.
# decode_record() doesn't support OCCURS yet (phase.md Phase 8, still
# open), so this one can't be cross-checked against it directly - bytes
# are instead hand-computed and verified against the same leaf-level
# decode_display()/decode_alpha() primitives decode_record() would
# itself dispatch to, applied by hand per occurrence, before being
# hardcoded into the Go main.
_OCCURS_GO_MAIN = """package main

import "fmt"

func main() {
	data := []byte{
		0xF1, 0xF2, 0xF3, 0xF4, 0xF0, 0xF3, 0xE6, 0xC9, 0xC4, 0xC7,
		0xC5, 0xE3, 0x40, 0x40, 0x40, 0x40, 0xF0, 0xF0, 0xF1, 0xF0,
		0xC7, 0xC1, 0xC4, 0xC7, 0xC5, 0xE3, 0x40, 0x40, 0x40, 0x40,
		0xF0, 0xF0, 0xF2, 0xF5, 0xC7, 0xC9, 0xE9, 0xD4, 0xD6, 0x40,
		0x40, 0x40, 0x40, 0x40, 0xF0, 0xF0, 0xF0, 0xF7, 0x40, 0x40,
		0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0xF0, 0xF0,
		0xF0, 0xF0, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40, 0x40,
		0x40, 0x40, 0xF0, 0xF0, 0xF0, 0xF0,
	}
	r, err := NewInventoryRecord(data)
	if err != nil {
		panic(err)
	}
	if v, err := r.WarehouseId(); err != nil || v != 1234 {
		panic(fmt.Sprintf("WarehouseId: got (%v, %v), want (1234, nil)", v, err))
	}
	if v, err := r.ItemCount(); err != nil || v != 3 {
		panic(fmt.Sprintf("ItemCount: got (%v, %v), want (3, nil)", v, err))
	}
	wantSkus := []string{"WIDGET    ", "GADGET    ", "GIZMO     ", "          ", "          "}
	wantQtys := []int16{10, 25, 7, 0, 0}
	for i := 0; i < 5; i++ {
		item, err := r.ItemTable(i)
		if err != nil {
			panic(fmt.Sprintf("ItemTable(%d): %v", i, err))
		}
		if sku := item.ItemSku(); sku != wantSkus[i] {
			panic(fmt.Sprintf("ItemTable(%d).ItemSku: got %q, want %q", i, sku, wantSkus[i]))
		}
		if qty, err := item.ItemQty(); err != nil || qty != wantQtys[i] {
			panic(fmt.Sprintf(
				"ItemTable(%d).ItemQty: got (%v, %v), want (%d, nil)", i, qty, err, wantQtys[i],
			))
		}
	}
	if _, err := r.ItemTable(5); err == nil {
		panic("ItemTable(5): want an out-of-range error, got nil")
	}
	fmt.Println("OCCURS Go decoder round-trip: OK")
}
"""


# REDEFINES overlay dispatch (Phase 10, eighth slice): the real
# redefines_overlay.cpy fixture, dispatched by PAYMENT-TYPE. Two full
# records (one "C", one "K") plus a third with an unmatched
# discriminator. decode_record() already decodes both overlaid views
# independently for a given byte string (it doesn't pick one), so the
# expected field values were cross-checked against it directly - same
# discipline as every other case, just confirming both interpretations
# decode cleanly, since picking which one is "active" is exactly the
# new behavior this slice adds and decode_record() doesn't have it.
_REDEFINES_DISPATCH = {
    "CARD-DATA": RedefinesDispatch(
        discriminator="PAYMENT-TYPE",
        rules=(
            RedefinesRule(value="C", variant="CARD-DATA"),
            RedefinesRule(value="K", variant="CHECK-DATA"),
        ),
    ),
}

_REDEFINES_GO_MAIN = """package main

import "fmt"

func main() {
	cardData := []byte{
		0xC3, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9,
		0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xF0,
		0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF1, 0xF2, 0xF2, 0xF5,
	}
	checkData := []byte{
		0xD2, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9,
		0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xF0,
		0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xF0,
	}
	unknownData := []byte{
		0xE7, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9,
		0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xF0,
		0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF1, 0xF2, 0xF2, 0xF5,
	}

	rCard, err := NewPaymentRecord(cardData)
	if err != nil {
		panic(err)
	}
	overlay, err := rCard.CardData()
	if err != nil {
		panic(err)
	}
	card, ok := overlay.(CardData)
	if !ok {
		panic(fmt.Sprintf("CardData(): got %T, want CardData", overlay))
	}
	if v := card.CardNumber(); v != "1234567890123456" {
		panic(fmt.Sprintf("CardNumber: got %q, want %q", v, "1234567890123456"))
	}
	if v, err := card.CardExp(); err != nil || v != 1225 {
		panic(fmt.Sprintf("CardExp: got (%v, %v), want (1225, nil)", v, err))
	}

	rCheck, err := NewPaymentRecord(checkData)
	if err != nil {
		panic(err)
	}
	overlay, err = rCheck.CardData()
	if err != nil {
		panic(err)
	}
	check, ok := overlay.(CheckData)
	if !ok {
		panic(fmt.Sprintf("CardData(): got %T, want CheckData", overlay))
	}
	if v, err := check.CheckNumber(); err != nil || v != 1234567890 {
		panic(fmt.Sprintf("CheckNumber: got (%v, %v), want (1234567890, nil)", v, err))
	}
	if v, err := check.BankRouting(); err != nil || v != 123456789 {
		panic(fmt.Sprintf("BankRouting: got (%v, %v), want (123456789, nil)", v, err))
	}

	rUnknown, err := NewPaymentRecord(unknownData)
	if err != nil {
		panic(err)
	}
	if _, err := rUnknown.CardData(); err == nil {
		panic("CardData() with an unmatched discriminator: want an error, got nil")
	}

	fmt.Println("REDEFINES dispatch Go decoder round-trip: OK")
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
    out_dir: pathlib.Path,
    label: str,
    source: str,
    go_main: str,
    redefines: dict[str, RedefinesDispatch] | None = None,
) -> bool:
    dsl = build_dsl(parse_copybook(source), source_file=f"{label}.cpy")
    resolved = resolve_mapping(recommend_mappings(dsl, "go"), Overrides())
    decoder_src = generate_go_decoder(dsl, resolved, redefines=redefines).replace(
        "package generated", "package main", 1
    )

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
    # values Python's own decode_record() already verified (except the
    # OCCURS case below, where decode_record() itself doesn't support
    # OCCURS yet - see its own comment). Eight cases: flat_display.cpy
    # (DISPLAY only), a synthetic DISPLAY+COMP-3+binary record (no
    # existing fixture combines those three within this slice's scope,
    # since mixed_usage.cpy also has COMP-1/COMP-2, which isn't
    # supported yet), nested_groups.cpy (nested group structs), a
    # synthetic record covering all three non-default sign placements
    # (no fixture uses SIGN at all), a synthetic record covering big.Int
    # across every supported usage/sign placement (no fixture has a
    # field wide enough to need it), a synthetic record covering plain
    # alphanumeric decode (no fixture has a PIC X/A field within this
    # slice's scope alone), occurs_table.cpy (leaf OCCURS count sibling
    # to a group OCCURS, exercising the indexed-accessor/reslice
    # mechanism end to end, including an out-of-range index), and
    # redefines_overlay.cpy (REDEFINES overlay dispatch: one record per
    # discriminator value, plus an unmatched one).
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
    ok = ok and _check_go_decoder_roundtrip(
        out_dir, "alpha", _ALPHA_SOURCE, _ALPHA_GO_MAIN
    )
    ok = ok and _check_go_decoder_roundtrip(
        out_dir, "occurs", (FIXTURES_DIR / "occurs_table.cpy").read_text(), _OCCURS_GO_MAIN,
    )
    ok = ok and _check_go_decoder_roundtrip(
        out_dir, "redefines", (FIXTURES_DIR / "redefines_overlay.cpy").read_text(),
        _REDEFINES_GO_MAIN, _REDEFINES_DISPATCH,
    )

    shutil.rmtree(out_dir)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

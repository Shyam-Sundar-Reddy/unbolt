import pytest

from unbolt.dsl import build_dsl
from unbolt.exceptions import UnsupportedDecodeError
from unbolt.generators.go_decoder import generate_go_decoder
from unbolt.generators.resolve import resolve_mapping
from unbolt.mapping import recommend_mappings
from unbolt.overrides import Overrides, apply_override
from unbolt.parser import parse_copybook


def _generate(source: str, overrides: Overrides | None = None) -> str:
    dsl = build_dsl(parse_copybook(source), source_file="<test>")
    overrides = overrides if overrides is not None else Overrides()
    report = recommend_mappings(dsl, "go")
    resolved = resolve_mapping(report, overrides)
    return generate_go_decoder(dsl, resolved)


def test_flat_record_emits_a_struct_with_a_constructor_and_accessors() -> None:
    out = _generate(
        """
        01  REC.
            05  AGE PIC S9(3).
        """
    )
    assert "type Rec struct {" in out
    assert "buf []byte" in out
    assert "func NewRec(buf []byte) (*Rec, error) {" in out
    assert "if len(buf) != 3 {" in out
    assert "func (r *Rec) Age() (int16, error) {" in out


def test_unsigned_field_decodes_without_a_sign_check() -> None:
    out = _generate("01 REC.\n  05 ID PIC 9(6).")
    assert "func (r *Rec) Id() (int32, error) {" in out
    assert "zone" not in out  # unsigned path has no sign nibble logic


def test_signed_field_includes_overpunch_sign_logic() -> None:
    out = _generate("01 REC.\n  05 AGE PIC S9(3).")
    assert "zone := last & 0xF0" in out
    assert "case 0xD0:" in out


def test_scaled_decimal_field_emits_plain_int64() -> None:
    out = _generate("01 REC.\n  05 AMT PIC S9(7)V99.")
    assert "func (r *Rec) Amt() (int64, error) {" in out


def test_accessor_offsets_match_field_positions() -> None:
    out = _generate(
        """
        01  REC.
            05  A PIC 9(3).
            05  B PIC 9(2).
        """
    )
    assert "r.buf[0:3]" in out
    assert "r.buf[3:5]" in out


def test_multiple_roots_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="exactly one DSL root"):
        _generate("01 A.\n  05 X PIC 9(1).\n01 B.\n  05 Y PIC 9(1).")


def test_scalar_root_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="root must be a group"):
        _generate("01 X PIC 9(1).")


def test_occurs_field_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="OCCURS"):
        _generate("01 REC.\n  05 A PIC 9(1) OCCURS 3 TIMES.")


def test_redefines_field_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="REDEFINES"):
        _generate("01 REC.\n  05 A PIC 9(3).\n  05 B REDEFINES A PIC X(3).")


def test_nested_group_gets_its_own_struct_and_accessor() -> None:
    out = _generate(
        """
        01  REC.
            05  GRP.
                10  A PIC 9(1).
        """
    )
    assert "type Grp struct {" in out
    assert "func (r *Rec) Grp() Grp {" in out
    assert "return Grp{buf: r.buf}" in out
    assert "func (r *Grp) A() (int8, error) {" in out


def test_nested_group_field_offsets_are_absolute_from_the_root() -> None:
    out = _generate(
        """
        01  REC.
            05  A PIC 9(2).
            05  GRP.
                10  B PIC 9(3).
        """
    )
    assert "r.buf[2:5]" in out  # GRP.B starts at absolute offset 2, not 0


def test_doubly_nested_groups_each_get_their_own_struct() -> None:
    out = _generate(
        """
        01  REC.
            05  OUTER.
                10  INNER.
                    15  A PIC 9(1).
        """
    )
    assert "type Outer struct {" in out
    assert "type Inner struct {" in out
    assert "func (r *Rec) Outer() Outer {" in out
    assert "func (r *Outer) Inner() Inner {" in out
    assert "func (r *Inner) A() (int8, error) {" in out


def test_nested_occurs_group_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="OCCURS"):
        _generate("01 REC.\n  05 GRP OCCURS 3 TIMES.\n    10 A PIC 9(1).")


def test_nested_redefines_group_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="REDEFINES"):
        _generate(
            """
            01  REC.
                05  A.
                    10  X PIC 9(1).
                05  B REDEFINES A.
                    10  Y PIC 9(1).
            """
        )


def test_alphanumeric_field_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="alphanumeric"):
        _generate("01 REC.\n  05 A PIC X(3).")


def test_comp1_field_is_unsupported() -> None:
    dsl = build_dsl(parse_copybook("01 REC.\n  05 A COMP-1."), source_file="<test>")
    report = recommend_mappings(dsl, "go")
    overrides = apply_override(
        Overrides(), "REC.A", "float32", "forced", valid_choices=[], force=True
    )
    resolved = resolve_mapping(report, overrides)
    with pytest.raises(UnsupportedDecodeError, match="COMP-1/COMP-2"):
        generate_go_decoder(dsl, resolved)


def test_packed_decimal_field_decodes_via_the_shared_helper() -> None:
    out = _generate("01 REC.\n  05 AMT PIC S9(9) COMP-3.")
    assert "func (r *Rec) Amt() (int32, error) {" in out
    assert "decodePackedDecimal(raw, 9)" in out
    assert "func decodePackedDecimal(raw []byte, digits int) (int64, error) {" in out


def test_packed_decimal_helper_is_only_emitted_once() -> None:
    out = _generate(
        """
        01  REC.
            05  A PIC S9(3) COMP-3.
            05  B PIC S9(4) COMP-3.
        """
    )
    assert out.count("func decodePackedDecimal(") == 1


def test_binary_unsigned_field_uses_encoding_binary() -> None:
    out = _generate("01 REC.\n  05 ID PIC 9(5) COMP.")
    assert 'import (\n\t"encoding/binary"\n\t"fmt"\n)' in out
    assert "func (r *Rec) Id() (int32, error) {" in out
    assert "binary.BigEndian.Uint32(raw)" in out


def test_binary_signed_field_sign_extends_via_cast() -> None:
    out = _generate("01 REC.\n  05 AMT PIC S9(9) COMP.")
    assert "int32(binary.BigEndian.Uint32(raw))" in out


def test_no_binary_import_when_no_binary_field_present() -> None:
    out = _generate("01 REC.\n  05 A PIC 9(3).")
    assert "encoding/binary" not in out


def test_leading_overpunch_sign_decodes() -> None:
    out = _generate("01 REC.\n  05 A PIC S9(3) SIGN IS LEADING.")
    assert "func (r *Rec) A() (int16, error) {" in out
    assert "first := raw[0]" in out
    assert "rest := raw[1:]" in out


def test_trailing_separate_sign_decodes() -> None:
    out = _generate("01 REC.\n  05 A PIC S9(3) SIGN IS SEPARATE.")
    assert "func (r *Rec) A() (int16, error) {" in out
    assert "digits, sign := raw[:len(raw)-1], raw[len(raw)-1]" in out
    assert "case 0x4E:" in out
    assert "case 0x60:" in out


def test_leading_separate_sign_decodes() -> None:
    out = _generate("01 REC.\n  05 A PIC S9(3) SIGN IS LEADING SEPARATE.")
    assert "func (r *Rec) A() (int16, error) {" in out
    assert "sign, digits := raw[0], raw[1:]" in out


def test_big_int_resolved_type_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="isn't supported in this slice"):
        _generate("01 REC.\n  05 A PIC S9(19).")


def test_forced_string_override_is_unsupported() -> None:
    dsl = build_dsl(parse_copybook("01 REC.\n  05 A PIC 9(3)."), source_file="<test>")
    report = recommend_mappings(dsl, "go")
    overrides = apply_override(
        Overrides(), "REC.A", "string", "forced", valid_choices=[], force=True
    )
    resolved = resolve_mapping(report, overrides)
    with pytest.raises(UnsupportedDecodeError, match="isn't supported in this slice"):
        generate_go_decoder(dsl, resolved)

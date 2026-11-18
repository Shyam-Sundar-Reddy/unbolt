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


def test_nested_group_field_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="group/nested"):
        _generate("01 REC.\n  05 GRP.\n    10 A PIC 9(1).")


def test_alphanumeric_field_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="alphanumeric"):
        _generate("01 REC.\n  05 A PIC X(3).")


def test_non_display_usage_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="only DISPLAY"):
        _generate("01 REC.\n  05 A PIC 9(5) COMP.")


def test_sign_separate_field_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="SIGN IS SEPARATE"):
        _generate("01 REC.\n  05 A PIC S9(3) SIGN IS SEPARATE.")


def test_sign_leading_field_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="SIGN IS LEADING"):
        _generate("01 REC.\n  05 A PIC S9(3) SIGN IS LEADING.")


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

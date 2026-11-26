import pytest

from unbolt.dsl import build_dsl
from unbolt.exceptions import UnsupportedDecodeError
from unbolt.generators.java_decoder import generate_java_decoder
from unbolt.generators.resolve import resolve_mapping
from unbolt.mapping import recommend_mappings
from unbolt.overrides import Overrides, apply_override
from unbolt.parser import parse_copybook


def _generate(source: str, overrides: Overrides | None = None) -> dict[str, str]:
    dsl = build_dsl(parse_copybook(source), source_file="<test>")
    overrides = overrides if overrides is not None else Overrides()
    report = recommend_mappings(dsl, "java")
    resolved = resolve_mapping(report, overrides)
    return generate_java_decoder(dsl, resolved)


def test_flat_record_emits_a_class_with_a_constructor_and_getters() -> None:
    out = _generate(
        """
        01  REC.
            05  AGE PIC S9(3).
        """
    )["Rec"]
    assert "public class Rec {" in out
    assert "private final java.nio.ByteBuffer buf;" in out
    assert "public Rec(java.nio.ByteBuffer buf) {" in out
    assert "if (buf.capacity() != 3) {" in out
    assert "public short getAge() {" in out


def test_one_compilation_unit_per_root() -> None:
    out = _generate("01 A.\n  05 X PIC 9(1).\n01 B.\n  05 Y PIC 9(1).")
    assert set(out) == {"A", "B"}


def test_unsigned_field_decodes_without_a_sign_check() -> None:
    out = _generate("01 REC.\n  05 ID PIC 9(6).")["Rec"]
    assert "public int getId() {" in out
    assert "zone" not in out  # unsigned path has no sign nibble logic


def test_signed_field_includes_overpunch_sign_logic() -> None:
    out = _generate("01 REC.\n  05 A PIC S9(3).")["Rec"]
    assert "case 0xC0:" in out
    assert "case 0xD0:" in out
    assert "v = -v;" in out


def test_byte_comparisons_mask_the_signed_java_byte_type() -> None:
    out = _generate("01 REC.\n  05 ID PIC 9(3).")["Rec"]
    assert "buf.get(i) & 0xFF" in out


def test_offsets_are_absolute_and_correct_for_a_second_field() -> None:
    out = _generate("01 REC.\n  05 A PIC 9(2).\n  05 B PIC 9(3).")["Rec"]
    assert "for (int i = 0; i < 2; i++)" in out
    assert "for (int i = 2; i < 5; i++)" in out


def test_scalar_root_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="must be a group"):
        _generate("01 X PIC 9(3).")


def test_occurs_field_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="OCCURS"):
        _generate("01 REC.\n  05 A PIC 9(1) OCCURS 3 TIMES.")


def test_redefines_field_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="REDEFINES"):
        _generate("01 REC.\n  05 A PIC 9(3).\n  05 B REDEFINES A PIC X(3).")


def test_nested_group_field_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="nested group"):
        _generate("01 REC.\n  05 GRP.\n    10 A PIC 9(3).")


def test_alphanumeric_field_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="alphanumeric"):
        _generate("01 REC.\n  05 A PIC X(3).")


def test_comp1_field_is_unsupported() -> None:
    dsl = build_dsl(parse_copybook("01 REC.\n  05 A COMP-1."), source_file="<test>")
    report = recommend_mappings(dsl, "java")
    overrides = apply_override(
        Overrides(), "REC.A", "float", "forced", valid_choices=[], force=True
    )
    resolved = resolve_mapping(report, overrides)
    with pytest.raises(UnsupportedDecodeError, match="COMP-1/COMP-2"):
        generate_java_decoder(dsl, resolved)


def test_non_display_usage_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="only DISPLAY fields"):
        _generate("01 REC.\n  05 A PIC S9(5) COMP-3.")


def test_sign_separate_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="SIGN IS SEPARATE/LEADING"):
        _generate("01 REC.\n  05 A PIC S9(3) SIGN IS SEPARATE.")


def test_sign_leading_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="SIGN IS SEPARATE/LEADING"):
        _generate("01 REC.\n  05 A PIC S9(3) SIGN IS LEADING.")


def test_big_integer_resolved_type_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="isn't supported in this slice"):
        _generate("01 REC.\n  05 A PIC S9(19).")


def test_decimal_field_resolving_to_bigdecimal_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="isn't supported in this slice"):
        _generate("01 REC.\n  05 A PIC S9(5)V99.")


def test_forced_string_override_is_unsupported() -> None:
    dsl = build_dsl(parse_copybook("01 REC.\n  05 A PIC 9(3)."), source_file="<test>")
    report = recommend_mappings(dsl, "java")
    overrides = apply_override(
        Overrides(), "REC.A", "String", "forced", valid_choices=[], force=True
    )
    resolved = resolve_mapping(report, overrides)
    with pytest.raises(UnsupportedDecodeError, match="isn't supported in this slice"):
        generate_java_decoder(dsl, resolved)

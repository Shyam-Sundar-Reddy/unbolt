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


def test_nested_group_gets_its_own_static_class_and_accessor() -> None:
    out = _generate("01 REC.\n  05 GRP.\n    10 A PIC 9(3).")["Rec"]
    assert "public Grp getGrp() {" in out
    assert "return new Grp(buf);" in out
    assert "public static class Grp {" in out
    assert "Grp(java.nio.ByteBuffer buf) {" in out
    assert "public short getA() {" in out


def test_doubly_nested_group_preserves_absolute_offsets() -> None:
    out = _generate(
        "01 REC.\n"
        "  05 HEADER.\n"
        "    10 ID PIC 9(8).\n"
        "    10 DATE.\n"
        "      15 YEAR PIC 9(4).\n"
        "      15 MONTH PIC 9(2).\n"
    )["Rec"]
    assert "public static class Header {" in out
    assert "public static class Date {" in out
    assert "for (int i = 0; i < 8; i++)" in out  # ID, absolute from the record root
    assert "for (int i = 8; i < 12; i++)" in out  # YEAR
    assert "for (int i = 12; i < 14; i++)" in out  # MONTH


def test_nested_occurs_group_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="OCCURS"):
        _generate("01 REC.\n  05 GRP OCCURS 3 TIMES.\n    10 A PIC 9(1).")


def test_nested_redefines_group_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="REDEFINES"):
        _generate(
            "01 REC.\n  05 A.\n    10 X PIC 9(3).\n  05 B REDEFINES A.\n    10 Y PIC 9(3)."
        )


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


def test_packed_decimal_field_decodes_via_the_shared_helper() -> None:
    out = _generate("01 REC.\n  05 A PIC S9(9) COMP-3.")["Rec"]
    assert "public int getA() {" in out
    assert "long v = decodePackedDecimal(buf, 0, 5, 9);" in out
    assert "private static long decodePackedDecimal(" in out


def test_packed_decimal_helper_emitted_once_even_with_two_fields() -> None:
    out = _generate("01 REC.\n  05 A PIC S9(5) COMP-3.\n  05 B PIC S9(5) COMP-3.")["Rec"]
    assert out.count("private static long decodePackedDecimal(") == 1


def test_signed_binary_field_reads_via_bytebuffer_natively() -> None:
    out = _generate("01 REC.\n  05 A PIC S9(9) COMP.")["Rec"]
    assert "public int getA() {" in out
    assert "int raw = buf.getInt(0);" in out
    assert "return (int) raw;" in out
    assert "decodePackedDecimal" not in out


def test_unsigned_binary_field_masks_and_widens() -> None:
    out = _generate("01 REC.\n  05 A PIC 9(4) COMP.")["Rec"]
    assert "short raw = buf.getShort(0);" in out
    assert "return (short) (raw & 0xFFFF);" in out


def test_unsigned_8_byte_binary_field_needs_no_mask() -> None:
    # Its 18-digit ceiling (datatypes/sizing.py's own BINARY tier
    # limit) means its max value always fits within long's own signed
    # range - there's no wider primitive to widen into, and none is
    # needed.
    out = _generate("01 REC.\n  05 A PIC 9(18) COMP.")["Rec"]
    assert "public long getA() {" in out
    assert "long raw = buf.getLong(0);" in out
    assert "return (long) raw;" in out
    assert "&" not in out


def test_non_display_non_packed_non_binary_usage_is_unsupported() -> None:
    dsl = build_dsl(parse_copybook("01 REC.\n  05 A COMP-1."), source_file="<test>")
    report = recommend_mappings(dsl, "java")
    overrides = apply_override(
        Overrides(), "REC.A", "int", "forced", valid_choices=[], force=True
    )
    resolved = resolve_mapping(report, overrides)
    with pytest.raises(UnsupportedDecodeError, match="COMP-1/COMP-2"):
        generate_java_decoder(dsl, resolved)


def test_leading_overpunch_sign_decodes() -> None:
    out = _generate("01 REC.\n  05 A PIC S9(3) SIGN IS LEADING.")["Rec"]
    assert "public short getA() {" in out
    assert "int first = buf.get(0) & 0xFF;" in out
    assert "for (int i = 1; i < 3; i++) {" in out
    assert "case 0xD0:" in out


def test_trailing_separate_sign_decodes() -> None:
    out = _generate("01 REC.\n  05 A PIC S9(3) SIGN IS SEPARATE.")["Rec"]
    assert "public short getA() {" in out
    assert "int sign = buf.get(3) & 0xFF;" in out
    assert "for (int i = 0; i < 3; i++) {" in out
    assert "case 0x4E:" in out
    assert "case 0x60:" in out


def test_leading_separate_sign_decodes() -> None:
    out = _generate("01 REC.\n  05 A PIC S9(3) SIGN IS LEADING SEPARATE.")["Rec"]
    assert "public short getA() {" in out
    assert "int sign = buf.get(0) & 0xFF;" in out
    assert "for (int i = 1; i < 4; i++) {" in out


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

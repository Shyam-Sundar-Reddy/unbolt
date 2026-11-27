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


def test_leaf_occurs_field_gets_an_indexed_accessor() -> None:
    out = _generate("01 REC.\n  05 A PIC 9(1) OCCURS 3 TIMES.")["Rec"]
    assert "public byte getA(int index) {" in out
    assert "if (index < 0 || index >= 3) {" in out
    assert (
        'throw new IllegalArgumentException("A: index " + index + " out of range [0, 3)");'
        in out
    )
    assert "int start = index * 1;" in out
    assert "int end = start + 1;" in out


def test_leaf_occurs_on_alpha_field_works() -> None:
    out = _generate("01 REC.\n  05 A PIC X(2) OCCURS 3 TIMES.")["Rec"]
    assert "public String getA(int index) {" in out
    assert "bytes[i - start] = buf.get(i);" in out


def test_leaf_occurs_on_big_integer_field_works() -> None:
    dsl = build_dsl(parse_copybook("01 REC.\n  05 A PIC S9(19) OCCURS 2 TIMES."), source_file="<t>")
    report = recommend_mappings(dsl, "java")
    resolved = resolve_mapping(report, Overrides())
    out = generate_java_decoder(dsl, resolved)["Rec"]
    assert "public java.math.BigInteger getA(int index) {" in out
    assert "int start = index * 19;" in out


def test_leaf_occurs_with_separate_sign_works() -> None:
    out = _generate("01 REC.\n  05 A PIC S9(3) SIGN IS SEPARATE OCCURS 3 TIMES.")["Rec"]
    assert "public short getA(int index) {" in out
    assert "int sign = buf.get(end - 1) & 0xFF;" in out


def test_occurs_field_with_redefines_still_rejected_for_redefines() -> None:
    dsl = build_dsl(
        parse_copybook(
            "01 REC.\n  05 A PIC 9(3) OCCURS 3 TIMES.\n  05 B REDEFINES A PIC X(3) OCCURS 3 TIMES."
        ),
        source_file="<t>",
    )
    report = recommend_mappings(dsl, "java")
    resolved = resolve_mapping(report, Overrides())
    with pytest.raises(UnsupportedDecodeError, match="REDEFINES"):
        generate_java_decoder(dsl, resolved)


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


def test_occurs_group_gets_an_indexed_accessor_with_a_base_field() -> None:
    out = _generate("01 REC.\n  05 GRP OCCURS 3 TIMES.\n    10 A PIC 9(1).")["Rec"]
    assert "public Grp getGrp(int index) {" in out
    assert "if (index < 0 || index >= 3) {" in out
    assert "int newBase = index * 1;" in out
    assert "return new Grp(buf, newBase);" in out
    assert "public static class Grp {" in out
    assert "private final int base;" in out
    assert "Grp(java.nio.ByteBuffer buf, int base) {" in out
    assert "public byte getA() {" in out
    assert "int start = this.base;" in out


def test_occurs_inside_occurs_rebases_independently_per_level() -> None:
    out = _generate(
        "01 REC.\n  05 OUTER OCCURS 2 TIMES.\n    10 INNER OCCURS 3 TIMES.\n      15 A PIC 9(1)."
    )["Rec"]
    assert "public Outer getOuter(int index) {" in out
    assert "int newBase = index * 3;" in out
    assert "public Inner getInner(int index) {" in out
    assert "int newBase = this.base + index * 1;" in out
    assert "public byte getA() {" in out
    assert "int start = this.base;" in out


def test_nested_redefines_group_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="REDEFINES"):
        _generate(
            "01 REC.\n  05 A.\n    10 X PIC 9(3).\n  05 B REDEFINES A.\n    10 Y PIC 9(3)."
        )


def test_alphanumeric_field_decodes_via_the_shared_cp037_charset() -> None:
    out = _generate("01 REC.\n  05 A PIC X(3).")["Rec"]
    assert "public String getA() {" in out
    assert "return new String(bytes, CP037);" in out
    assert (
        'private static final java.nio.charset.Charset CP037 = '
        'java.nio.charset.Charset.forName("Cp037");'
    ) in out


def test_alpha_pic_variant_decodes_the_same_way() -> None:
    out = _generate("01 REC.\n  05 A PIC A(3).")["Rec"]
    assert "public String getA() {" in out
    assert "return new String(bytes, CP037);" in out


def test_edited_picture_field_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="edited/national"):
        _generate("01 REC.\n  05 A PIC ZZZ9.")


def test_national_picture_field_is_unsupported() -> None:
    with pytest.raises(UnsupportedDecodeError, match="edited/national"):
        _generate("01 REC.\n  05 A PIC N(3).")


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


def test_unsigned_big_integer_field_decodes_via_the_shared_display_helper() -> None:
    out = _generate("01 REC.\n  05 A PIC 9(20).")["Rec"]
    assert "public java.math.BigInteger getA() {" in out
    assert "return decodeDisplayDigitsBig(buf, 0, 20);" in out
    assert "private static java.math.BigInteger decodeDisplayDigitsBig(" in out
    assert "decodePackedDecimalBig" not in out


def test_trailing_overpunch_big_integer_field_decodes() -> None:
    out = _generate("01 REC.\n  05 A PIC S9(19).")["Rec"]
    assert "public java.math.BigInteger getA() {" in out
    assert "decodeDisplayDigitsBig(buf, 0, 18)" in out
    assert "v = v.negate();" in out


def test_leading_overpunch_big_integer_field_decodes() -> None:
    out = _generate("01 REC.\n  05 A PIC S9(19) SIGN IS LEADING.")["Rec"]
    assert "java.math.BigInteger tail = decodeDisplayDigitsBig(buf, 1, 19);" in out
    assert "java.math.BigInteger scale = java.math.BigInteger.TEN.pow(18);" in out


def test_trailing_separate_sign_big_integer_field_decodes() -> None:
    out = _generate("01 REC.\n  05 A PIC S9(19) SIGN IS SEPARATE.")["Rec"]
    assert "int sign = buf.get(19) & 0xFF;" in out
    assert "case 0x60:\n                return v.negate();" in out


def test_leading_separate_sign_big_integer_field_decodes() -> None:
    out = _generate("01 REC.\n  05 A PIC S9(19) SIGN IS LEADING SEPARATE.")["Rec"]
    assert "int sign = buf.get(0) & 0xFF;" in out


def test_packed_big_integer_field_decodes_via_the_shared_packed_helper() -> None:
    out = _generate("01 REC.\n  05 A PIC S9(19) COMP-3.")["Rec"]
    assert "return decodePackedDecimalBig(buf, 0, 10, 19);" in out
    assert "private static java.math.BigInteger decodePackedDecimalBig(" in out
    assert "decodeDisplayDigitsBig" not in out


def test_big_integer_binary_field_is_unsupported() -> None:
    dsl = build_dsl(parse_copybook("01 REC.\n  05 A PIC S9(3) COMP."), source_file="<test>")
    report = recommend_mappings(dsl, "java")
    overrides = apply_override(
        Overrides(), "REC.A", "BigInteger", "forced", valid_choices=["BigInteger"], force=True
    )
    resolved = resolve_mapping(report, overrides)
    with pytest.raises(UnsupportedDecodeError, match="only supported for DISPLAY/COMP-3"):
        generate_java_decoder(dsl, resolved)


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

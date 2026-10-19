from unbolt.dsl import build_dsl
from unbolt.generators.java import generate_java
from unbolt.generators.resolve import resolve_mapping
from unbolt.mapping import recommend_mappings
from unbolt.overrides import Overrides, apply_override
from unbolt.parser import parse_copybook


def _generate(source: str, overrides: Overrides | None = None) -> dict[str, str]:
    dsl = build_dsl(parse_copybook(source), source_file="<test>")
    report = recommend_mappings(dsl, "java")
    overrides = overrides if overrides is not None else Overrides()
    resolved = resolve_mapping(report, overrides)
    return generate_java(dsl, resolved)


def test_flat_record_emits_one_public_class_with_getters_and_setters() -> None:
    (src,) = _generate(
        """
        01  REC.
            05  AGE PIC S9(3).
        """
    ).values()
    assert "public class Rec {" in src
    assert "private short age;" in src
    assert "public short getAge() { return age; }" in src
    assert "public void setAge(short age) { this.age = age; }" in src


def test_nested_group_is_textually_nested_inside_its_parents_braces() -> None:
    # Java has no floating top-level `static class` - it must be inside
    # the enclosing class's { }.
    (src,) = _generate(
        """
        01  REC.
            05  GRP.
                10  LEAF PIC 9(1).
        """
    ).values()
    class_start = src.index("public class Rec {")
    nested_start = src.index("public static class Grp {")
    class_end = src.rindex("}")
    assert class_start < nested_start < class_end


def test_validators_are_nested_inside_the_class_not_floating() -> None:
    (src,) = _generate("01 X PIC 9(3).").values()
    class_start = src.index("public class X {")
    validator_start = src.index("public static void validateX")
    class_end = src.rindex("}")
    assert class_start < validator_start < class_end


def test_long_validator_literals_get_an_l_suffix() -> None:
    # Java int literals outside +-2^31 don't compile without `L`.
    (src,) = _generate("01 X PIC S9(18).").values()
    assert "999999999999999999L" in src


def test_alphanumeric_field_maps_to_string() -> None:
    (src,) = _generate("01 REC PIC X(10).").values()
    assert "String value" in src


def test_occurs_emits_a_java_array() -> None:
    (src,) = _generate(
        """
        01  REC.
            05  ROW PIC 9(1) OCCURS 3 TIMES.
        """
    ).values()
    assert "byte[] row" in src


def test_redefines_emits_two_separate_fields_with_a_comment() -> None:
    (src,) = _generate(
        """
        01  REC.
            05  A PIC X(4).
            05  B REDEFINES A PIC 9(4).
        """
    ).values()
    assert "// REDEFINES A" in src


def test_bigdecimal_and_biginteger_get_imported() -> None:
    (src,) = _generate("01 X PIC S9(9)V99 COMP-3.").values()
    assert "import java.math.BigDecimal;" in src


def test_comp1_with_an_override_has_no_validator() -> None:
    overrides = apply_override(
        Overrides(), "REC.S", "float", "best-effort", valid_choices=[], force=True
    )
    (src,) = _generate("01 REC.\n    05 S COMP-1.", overrides).values()
    assert "private float s;" in src
    assert "validateS" not in src


def test_multiple_roots_produce_multiple_compilation_units() -> None:
    result = _generate(
        """
        01  A PIC 9(1).
        77  B PIC 9(1).
        """
    )
    assert set(result.keys()) == {"A", "B"}


def test_same_dsl_and_mapping_produce_byte_identical_output() -> None:
    source = "01 X PIC S9(7)V99."
    first = _generate(source)
    second = _generate(source)
    assert first == second

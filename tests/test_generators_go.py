from unbolt.dsl import build_dsl
from unbolt.generators.go import generate_go
from unbolt.generators.resolve import resolve_mapping
from unbolt.mapping import recommend_mappings
from unbolt.overrides import Overrides, apply_override
from unbolt.parser import parse_copybook


def _generate(source: str, overrides: Overrides | None = None) -> str:
    dsl = build_dsl(parse_copybook(source), source_file="<test>")
    overrides = overrides if overrides is not None else Overrides()
    report = recommend_mappings(dsl, "go")
    resolved = resolve_mapping(report, overrides)
    return generate_go(dsl, resolved)


def test_flat_record_emits_one_struct_with_resolved_field_types() -> None:
    out = _generate(
        """
        01  REC.
            05  AGE PIC S9(3).
        """
    )
    assert "type Rec struct {" in out
    assert "Age int16" in out


def test_nested_group_emits_a_separate_named_struct() -> None:
    out = _generate(
        """
        01  REC.
            05  GRP.
                10  LEAF PIC 9(1).
        """
    )
    assert "type Grp struct {" in out
    assert "Grp Grp" in out  # parent field referencing the nested type


def test_alphanumeric_field_maps_to_string() -> None:
    out = _generate("01 REC PIC X(10).")
    assert "string" in out


def test_occurs_emits_a_fixed_size_array() -> None:
    out = _generate(
        """
        01  REC.
            05  ROW PIC 9(1) OCCURS 3 TIMES.
        """
    )
    assert "[3]int8" in out


def test_redefines_emits_two_separate_fields_with_a_comment() -> None:
    # decision 0005: struct shape only, no real memory overlay yet.
    out = _generate(
        """
        01  REC.
            05  A PIC X(4).
            05  B REDEFINES A PIC 9(4).
        """
    )
    assert "B int16 // REDEFINES A" in out
    assert out.count("A string") == 1
    assert out.count("B int16") == 1


def test_validator_is_generated_for_a_narrower_than_type_field() -> None:
    out = _generate("01 X PIC 9(3).")
    assert "func ValidateX(v uint16) error {" in out or "func ValidateX(v int16) error {" in out
    assert "999" in out


def test_no_validator_for_bigint_fallback() -> None:
    out = _generate("01 X PIC S9(19).")
    assert "func ValidateX" not in out


def test_comp1_with_an_override_skips_validator_but_keeps_the_field() -> None:
    overrides = apply_override(
        Overrides(), "REC.S", "float32", "best-effort", valid_choices=[], force=True
    )
    out = _generate("01 REC.\n    05 S COMP-1.", overrides)
    assert "S float32" in out
    assert "func ValidateS" not in out


def test_same_dsl_and_mapping_produce_byte_identical_output() -> None:
    source = "01 X PIC S9(7)V99."
    first = _generate(source)
    second = _generate(source)
    assert first == second

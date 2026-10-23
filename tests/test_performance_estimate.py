from pathlib import Path

from unbolt.dsl import build_dsl
from unbolt.mapping import recommend_mappings
from unbolt.overrides import Overrides, apply_override
from unbolt.parser import parse_copybook
from unbolt.performance import estimate_storage

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _dsl(source: str):
    return build_dsl(parse_copybook(source), source_file="<test>")


def test_label_is_always_estimated() -> None:
    dsl = _dsl("01 X PIC 9(3).")
    (est,) = estimate_storage(dsl, recommend_mappings(dsl, "go"))
    assert est.label == "estimated"


def test_cobol_bytes_matches_the_dsl_byte_size_exactly() -> None:
    source = (FIXTURES_DIR / "flat_display.cpy").read_text()
    dsl = _dsl(source)
    (est,) = estimate_storage(dsl, recommend_mappings(dsl, "go"))
    assert est.cobol_record_bytes == 18  # matches docs/acceptance-criteria.md


def test_target_bytes_known_for_fixed_width_types() -> None:
    # PIC 9(3) (0..999) resolves to int16 - the first valid candidate in
    # ladder order (decision 0004), since int16 also covers an unsigned
    # field's range when sizes tie.
    dsl = _dsl("01 X PIC 9(3).")
    (est,) = estimate_storage(dsl, recommend_mappings(dsl, "go"))
    (field,) = est.fields
    assert field.target_type == "int16"
    assert field.target_bytes == 2
    assert est.target_record_bytes == 2


def test_target_bytes_unknown_for_variable_size_types() -> None:
    dsl = _dsl("01 X PIC S9(19).")  # overflows every fixed ladder type -> big.Int
    (est,) = estimate_storage(dsl, recommend_mappings(dsl, "go"))
    (field,) = est.fields
    assert field.target_type == "big.Int"
    assert field.target_bytes is None
    assert est.target_record_bytes is None  # never silently treated as 0


def test_occurs_multiplies_the_target_total_not_the_per_field_entry() -> None:
    source = (FIXTURES_DIR / "occurs_table.cpy").read_text()
    dsl = _dsl(source)
    (est,) = estimate_storage(dsl, recommend_mappings(dsl, "go"))

    sku = next(f for f in est.fields if f.field_path.endswith("ITEM-SKU"))
    qty = next(f for f in est.fields if f.field_path.endswith("ITEM-QTY"))
    assert (sku.cobol_bytes, sku.target_bytes) == (10, 10)  # one occurrence, not x5
    assert (qty.cobol_bytes, qty.target_bytes) == (4, 2)

    # 2 (warehouse) + 1 (count) + 5 * (10 + 2) = 63
    assert est.target_record_bytes == 63
    assert est.cobol_record_bytes == 76  # cross-checked by gnucobol_check


def test_alphanumeric_field_uses_its_own_cobol_length_as_target_bytes() -> None:
    dsl = _dsl("01 X PIC X(16).")
    (est,) = estimate_storage(dsl, recommend_mappings(dsl, "go"))
    (field,) = est.fields
    assert field.target_type == "string"
    assert field.target_bytes == 16


def test_java_target_uses_capitalized_string_type() -> None:
    dsl = _dsl("01 X PIC X(16).")
    (est,) = estimate_storage(dsl, recommend_mappings(dsl, "java"))
    (field,) = est.fields
    assert field.target_type == "String"


def test_comp1_with_a_forced_override_is_estimated_using_the_override() -> None:
    dsl = _dsl("01 REC.\n    05 S COMP-1.")
    mapping = recommend_mappings(dsl, "go")
    overrides = apply_override(
        Overrides(), "REC.S", "float32", "best-effort", valid_choices=[], force=True
    )
    (est,) = estimate_storage(dsl, mapping, overrides=overrides)
    (field,) = est.fields
    assert (field.target_type, field.target_bytes) == ("float32", 4)


def test_multiple_roots_each_get_their_own_estimate() -> None:
    dsl = _dsl("01 A PIC 9(1).\n77 B PIC 9(1).")
    estimates = estimate_storage(dsl, recommend_mappings(dsl, "go"))
    assert {e.root_name for e in estimates} == {"A", "B"}

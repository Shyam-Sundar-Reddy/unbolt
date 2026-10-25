from unbolt.dsl import build_dsl
from unbolt.generators import generate_code
from unbolt.mapping import recommend_mappings
from unbolt.overrides import Overrides, apply_override
from unbolt.parser import parse_copybook
from unbolt.parser.diagnostics import renames_unsupported
from unbolt.validation import validate_conversion


def _dsl(source: str):
    return build_dsl(parse_copybook(source), source_file="<test>")


def test_clean_conversion_has_no_findings() -> None:
    dsl = _dsl("01 X PIC 9(3).")
    mapping = recommend_mappings(dsl, "go")
    generated = generate_code(dsl, mapping, "go")
    report = validate_conversion(dsl, mapping, generated)
    assert report.findings == ()


def test_parser_diagnostics_are_rolled_up() -> None:
    dsl = _dsl("01 X PIC 9(3).")
    mapping = recommend_mappings(dsl, "go")
    generated = generate_code(dsl, mapping, "go")
    report = validate_conversion(
        dsl, mapping, generated, diagnostics=(renames_unsupported(7),)
    )
    assert [f.code for f in report.findings] == ["CBL-W020"]


def test_needs_policy_field_produces_a_finding() -> None:
    dsl = _dsl("01 REC.\n    05 S COMP-1.")
    mapping = recommend_mappings(dsl, "go")
    overrides = apply_override(
        Overrides(), "REC.S", "float32", "best-effort", valid_choices=[], force=True
    )
    generated = generate_code(dsl, mapping, "go", overrides=overrides)
    report = validate_conversion(dsl, mapping, generated)
    assert any(f.code == "needs-policy" and f.field_path == "REC.S" for f in report.findings)


def test_a_field_missing_from_generated_output_is_flagged() -> None:
    # Simulates the exact Phase 3 bug class: a field the mapping engine
    # knows about, but that never made it into the generated text.
    dsl = _dsl("01 X PIC 9(3).")
    mapping = recommend_mappings(dsl, "go")
    report = validate_conversion(dsl, mapping, {"gen.go": "package generated\n"})
    assert any(f.code == "missing-from-output" for f in report.findings)


def test_forced_invalid_override_is_flagged_even_though_a_valid_candidate_exists() -> None:
    # Regression: the old _needs_policy_findings only asked "does this
    # field have *any* valid candidate at all" - true here (BigDecimal is
    # valid), so it stayed silent even when the actually-chosen candidate
    # (double, status "invalid") was the hard-rule-rejected one.
    dsl = _dsl("01 X PIC S9(9)V99 COMP-3.")
    mapping = recommend_mappings(dsl, "java")
    overrides = apply_override(
        Overrides(), "X", "double", "best-effort", valid_choices=[], force=True
    )
    generated = generate_code(dsl, mapping, "java", overrides=overrides)
    report = validate_conversion(dsl, mapping, generated, overrides=overrides)
    (finding,) = [f for f in report.findings if f.field_path == "X"]
    assert finding.code == "forced-invalid-override"
    assert finding.severity == "error"
    assert "double" in finding.message
    assert not any(f.code == "needs-policy" for f in report.findings)


def test_needs_policy_finding_still_fires_without_overrides_passed() -> None:
    # The pre-existing no-overrides-argument call shape (every caller
    # before this fix) must keep working exactly as before.
    dsl = _dsl("01 REC.\n    05 S COMP-1.")
    mapping = recommend_mappings(dsl, "go")
    generated = generate_code(
        dsl, mapping, "go",
        overrides=apply_override(
            Overrides(), "REC.S", "float32", "best-effort", valid_choices=[], force=True
        ),
    )
    report = validate_conversion(dsl, mapping, generated)
    assert any(f.code == "needs-policy" and f.field_path == "REC.S" for f in report.findings)


def test_boundary_math_is_self_consistent_for_a_decimal_field() -> None:
    dsl = _dsl("01 X PIC S9(7)V99.")
    mapping = recommend_mappings(dsl, "go")
    generated = generate_code(dsl, mapping, "go")
    report = validate_conversion(dsl, mapping, generated)
    assert not any(f.code.startswith("boundary") for f in report.findings)
    assert not any(f.code == "precision-mismatch" for f in report.findings)

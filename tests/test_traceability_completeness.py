from pathlib import Path

import pytest

from unbolt.dsl import build_dsl
from unbolt.generators import generate_code
from unbolt.mapping import recommend_mappings
from unbolt.overrides import Overrides, apply_override
from unbolt.parser import parse_copybook
from unbolt.reporting import build_report
from unbolt.validation import validate_conversion

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
FIXTURE_NAMES = [p.stem for p in sorted(FIXTURES_DIR.glob("*.cpy"))]


def _overrides_for(name: str, target: str) -> Overrides:
    if name != "mixed_usage":
        return Overrides()
    float_type, double_type = ("float32", "float64") if target == "go" else ("float", "double")
    reason = "best-effort IEEE754 approximation (goal.md section 5.4)"
    overrides = apply_override(
        Overrides(),
        "FINANCIAL-RECORD.SENSOR-READING",
        float_type,
        reason,
        valid_choices=[],
        force=True,
    )
    return apply_override(
        overrides,
        "FINANCIAL-RECORD.PRECISE-READING",
        double_type,
        reason,
        valid_choices=[],
        force=True,
    )


@pytest.mark.parametrize("target", ["go", "java"])
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_every_mapped_field_has_a_complete_trace_entry(name: str, target: str) -> None:
    source = (FIXTURES_DIR / f"{name}.cpy").read_text()
    dsl = build_dsl(parse_copybook(source), source_file=f"{name}.cpy")
    mapping = recommend_mappings(dsl, target)
    overrides = _overrides_for(name, target)
    generated = generate_code(dsl, mapping, target, overrides=overrides)
    validation = validate_conversion(dsl, mapping, generated)
    report = build_report(dsl, mapping, validation, overrides=overrides)

    # "No gaps" means nothing is missing from the output - a needs-policy
    # warning (COMP-1/COMP-2 in mixed_usage) is an expected, informative
    # finding, not a gap: the field still has a complete trace entry below.
    assert not any(f.code == "missing-from-output" for f in validation.findings)

    expected_paths = {f.field_path for f in mapping.fields}
    traced_paths = {e.field_path for e in report.entries}
    assert traced_paths == expected_paths

    for entry in report.entries:
        assert entry.source_line >= 1
        assert entry.rule_id
        assert entry.rationale

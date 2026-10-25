import json

from unbolt.dsl import build_dsl
from unbolt.mapping import recommend_mappings
from unbolt.overrides import Overrides, apply_override
from unbolt.parser import parse_copybook
from unbolt.reporting import build_report, render_json, render_markdown
from unbolt.validation import validate_conversion


def _dsl(source: str):
    return build_dsl(parse_copybook(source), source_file="<test>")


def test_trace_entry_has_source_line_rule_and_rationale() -> None:
    dsl = _dsl("01 X PIC 9(3).")
    mapping = recommend_mappings(dsl, "go")
    validation = validate_conversion(dsl, mapping, {})
    report = build_report(dsl, mapping, validation)

    (entry,) = report.entries
    assert entry.field_path == "X"
    assert entry.source_line == 1
    assert entry.rule_id.startswith("go-int-")
    assert entry.rationale


def test_forced_override_traces_to_the_developers_own_reason() -> None:
    # COMP-1's only candidate is a needs-policy placeholder, not a type
    # match, so the normal candidate -> rule_id/rationale lookup can't
    # find "float32" among its candidates - must fall back to the
    # override's own stated reason instead of crashing.
    dsl = _dsl("01 REC.\n    05 S COMP-1.")
    mapping = recommend_mappings(dsl, "go")
    overrides = apply_override(
        Overrides(), "REC.S", "float32", "best-effort IEEE754", valid_choices=[], force=True
    )
    validation = validate_conversion(dsl, mapping, {})
    report = build_report(dsl, mapping, validation, overrides=overrides)

    (entry,) = report.entries
    assert entry.chosen_type == "float32"
    assert entry.rule_id == "override"
    assert entry.rationale == "best-effort IEEE754"


def test_forced_override_onto_a_rejected_candidate_does_not_self_contradict() -> None:
    # Regression: UNIT-PRICE's "double" candidate is real, just status
    # "invalid" - the old lookup matched it by name and reused its own
    # rejection rationale verbatim, printing double as "chosen" right next
    # to "rejected by default (hard rule)".
    dsl = _dsl("01 X PIC S9(9)V99 COMP-3.")
    mapping = recommend_mappings(dsl, "java")
    overrides = apply_override(
        Overrides(), "X", "double", "best-effort", valid_choices=[], force=True
    )
    validation = validate_conversion(dsl, mapping, {}, overrides=overrides)
    report = build_report(dsl, mapping, validation, overrides=overrides)

    (entry,) = report.entries
    assert entry.chosen_type == "double"
    assert entry.rule_id == "override-forced"
    # The developer's own reason leads; the rule engine's rejection is
    # kept as labeled context, not presented as the acceptance reason.
    assert entry.rationale.startswith("best-effort (rule engine status: invalid:")
    assert "rejected by default" in entry.rationale


def test_markdown_report_contains_the_field_and_its_rationale() -> None:
    dsl = _dsl("01 X PIC 9(3).")
    mapping = recommend_mappings(dsl, "go")
    validation = validate_conversion(dsl, mapping, {})
    report = build_report(dsl, mapping, validation)

    md = render_markdown(report)
    assert "`X`" in md
    assert "999" in md


def test_json_report_round_trips_the_same_fields() -> None:
    dsl = _dsl("01 X PIC 9(3).")
    mapping = recommend_mappings(dsl, "go")
    validation = validate_conversion(dsl, mapping, {})
    report = build_report(dsl, mapping, validation)

    data = json.loads(render_json(report))
    assert data["target"] == "go"
    assert data["entries"][0]["field_path"] == "X"


def test_findings_appear_in_both_renderings() -> None:
    dsl = _dsl("01 X PIC 9(3).")
    mapping = recommend_mappings(dsl, "go")
    validation = validate_conversion(dsl, mapping, {})  # empty generated -> missing-from-output
    report = build_report(dsl, mapping, validation)

    assert any(f.code == "missing-from-output" for f in report.findings)
    assert "missing-from-output" in render_markdown(report)
    assert "missing-from-output" in render_json(report)

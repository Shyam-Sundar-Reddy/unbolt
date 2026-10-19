import pytest

from unbolt.dsl import build_dsl
from unbolt.exceptions import UnknownTargetError
from unbolt.mapping import recommend_mappings
from unbolt.parser import parse_copybook


def _dsl(source: str):
    return build_dsl(parse_copybook(source), source_file="<test>")


def test_unknown_target_raises() -> None:
    with pytest.raises(UnknownTargetError):
        recommend_mappings(_dsl("01 X PIC 9(1)."), "rust")


def test_field_path_is_dot_joined_from_root() -> None:
    dsl = _dsl(
        """
        01  REC.
            05  GRP.
                10  LEAF PIC 9(1).
        """
    )
    report = recommend_mappings(dsl, "go")
    assert [f.field_path for f in report.fields] == ["REC.GRP.LEAF"]


def test_groups_and_alphanumeric_fields_produce_no_mapping() -> None:
    dsl = _dsl(
        """
        01  REC.
            05  NAME PIC X(10).
            05  AGE PIC 9(3).
        """
    )
    report = recommend_mappings(dsl, "go")
    # REC (group) and NAME (alphanumeric) aren't numeric mapping targets.
    assert [f.field_path for f in report.fields] == ["REC.AGE"]


def test_every_field_has_every_candidate_not_just_the_winner() -> None:
    dsl = _dsl("01 X PIC 9(3).")
    report = recommend_mappings(dsl, "go")
    (mapping,) = report.fields
    statuses = {c.status for c in mapping.candidates}
    assert "valid" in statuses
    assert "invalid" in statuses  # e.g. uint8/int8 too small for 0..999


def test_comp1_and_comp2_get_a_needs_policy_candidate_not_silent_omission() -> None:
    # goal.md §5.4: IBM hex float, not IEEE 754 - must be flagged, never
    # silently skipped. Regression test: these fields have no PIC and no
    # children, which an earlier version of walk() mistook for a group
    # (same bug shape as the Phase 1 builder.py fix) and dropped entirely.
    dsl = _dsl(
        """
        01  REC.
            05  S COMP-1.
            05  D COMP-2.
        """
    )
    report = recommend_mappings(dsl, "go")
    assert {f.field_path for f in report.fields} == {"REC.S", "REC.D"}
    for mapping in report.fields:
        assert [c.status for c in mapping.candidates] == ["needs-policy"]


def test_decimal_field_routes_to_decimal_rules_regardless_of_usage() -> None:
    # A DISPLAY field with a scale still needs decimal handling, not just
    # COMP-3 fields - scale, not USAGE, decides the routing.
    dsl = _dsl("01 X PIC S9(7)V99 DISPLAY.")
    report = recommend_mappings(dsl, "go")
    (mapping,) = report.fields
    type_names = {c.type_name for c in mapping.candidates}
    assert "int64 (scaled)" in type_names
    assert "uint16" not in type_names

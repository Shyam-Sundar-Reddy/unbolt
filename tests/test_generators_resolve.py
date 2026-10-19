import pytest

from unbolt.exceptions import UnapprovedMappingError
from unbolt.generators.resolve import resolve_mapping
from unbolt.mapping.model import Candidate, FieldMapping, MappingReport
from unbolt.overrides import Overrides, apply_override


def _report(*fields: FieldMapping) -> MappingReport:
    return MappingReport(target="go", fields=fields)


def test_resolves_to_the_first_valid_candidate_by_default() -> None:
    field = FieldMapping(
        "REC.AGE",
        (
            Candidate("int8", "invalid", "r1", "too small"),
            Candidate("int16", "valid", "r2", "fits"),
            Candidate("int32", "valid", "r3", "fits"),
        ),
    )
    resolved = resolve_mapping(_report(field), Overrides())
    assert resolved == {"REC.AGE": "int16"}


def test_an_override_wins_over_the_default() -> None:
    field = FieldMapping(
        "REC.AGE",
        (
            Candidate("int16", "valid", "r2", "fits"),
            Candidate("int32", "valid", "r3", "fits"),
        ),
    )
    overrides = apply_override(
        Overrides(),
        "REC.AGE",
        "int32",
        "prefer the wider type",
        valid_choices=["int16", "int32"],
    )
    resolved = resolve_mapping(_report(field), overrides)
    assert resolved == {"REC.AGE": "int32"}


def test_no_valid_candidate_and_no_override_is_unapproved() -> None:
    field = FieldMapping("REC.X", (Candidate("float32", "invalid", "r1", "bad"),))
    with pytest.raises(UnapprovedMappingError):
        resolve_mapping(_report(field), Overrides())

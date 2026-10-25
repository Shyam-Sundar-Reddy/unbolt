"""Candidate/report shape for the mapping engine.

A Candidate never represents a decision - it's one fact ("does this type
cover this field's range, and why/why not") out of possibly several for
the same field. recommend_mappings() always returns every candidate, not
just the winner; picking one is what Overrides/apply_override is for.
"""

from dataclasses import dataclass
from typing import Literal

Status = Literal["valid", "invalid", "needs-policy"]


@dataclass(frozen=True, slots=True)
class Candidate:
    type_name: str
    status: Status
    rule_id: str
    rationale: str


@dataclass(frozen=True, slots=True)
class FieldMapping:
    field_path: str
    candidates: tuple[Candidate, ...]


@dataclass(frozen=True, slots=True)
class MappingReport:
    target: str
    fields: tuple[FieldMapping, ...]


def candidate_names(report: MappingReport, field_path: str) -> tuple[str, ...]:
    """Every candidate type name for one field, or () if it isn't mapped.

    Includes `invalid`/`needs-policy` candidates - this is the full fact
    list, not an acceptance list. Use `valid_candidate_names()` to build
    `apply_override`'s `valid_choices` guard.
    """
    for field in report.fields:
        if field.field_path == field_path:
            return tuple(c.type_name for c in field.candidates)
    return ()


def valid_candidate_names(report: MappingReport, field_path: str) -> tuple[str, ...]:
    """Candidate type names with status == 'valid' for one field.

    Returns () if the field isn't mapped or has no valid candidate - an
    `invalid`/`needs-policy` candidate (e.g. Java `double` for a decimal
    field, rejected by the never-float-for-decimal hard rule) is not an
    acceptable default choice, only a forced (`force=True`) one.
    """
    for field in report.fields:
        if field.field_path == field_path:
            return tuple(c.type_name for c in field.candidates if c.status == "valid")
    return ()

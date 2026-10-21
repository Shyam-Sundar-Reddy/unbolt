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
    """Every candidate type name for one field, or () if it isn't mapped."""
    for field in report.fields:
        if field.field_path == field_path:
            return tuple(c.type_name for c in field.candidates)
    return ()

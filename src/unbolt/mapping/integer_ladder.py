"""Shared range-fit logic for integer type ladders (goal.md §5.7).

Both Go and Java candidates come from the same check: does this type's
own [min, max] fully cover the field's [min, max]? Only the ladder of
types differs between languages - Go has unsigned types, Java doesn't,
and that difference falls out naturally from checking real numbers
against each language's real type ranges, with no special-casing needed.
"""

from dataclasses import dataclass
from decimal import Decimal

from unbolt.datatypes import TypeFacts
from unbolt.mapping.model import Candidate, Status


@dataclass(frozen=True, slots=True)
class TypeSpec:
    name: str
    min_value: int
    max_value: int


def evaluate_integer_ladder(
    facts: TypeFacts, ladder: tuple[TypeSpec, ...], rule_prefix: str
) -> tuple[Candidate, ...]:
    candidates = []
    for spec in ladder:
        fits = Decimal(spec.min_value) <= facts.min_value and facts.max_value <= Decimal(
            spec.max_value
        )
        status: Status
        if fits:
            rationale = (
                f"{spec.name} holds {spec.min_value}..{spec.max_value}, "
                f"which covers the field's {facts.min_value}..{facts.max_value}"
            )
            status = "valid"
        else:
            rationale = (
                f"{spec.name} holds {spec.min_value}..{spec.max_value}, "
                f"too small for the field's {facts.min_value}..{facts.max_value}"
            )
            status = "invalid"
        candidates.append(
            Candidate(
                type_name=spec.name,
                status=status,
                rule_id=f"{rule_prefix}-{spec.name}",
                rationale=rationale,
            )
        )
    return tuple(candidates)

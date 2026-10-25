"""Developer decisions, stored apart from the immutable DSL and apart from
the mapping engine's candidate facts. Picking a candidate is a decision;
the candidates themselves are not.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from unbolt.exceptions import InvalidChoiceError


@dataclass(frozen=True, slots=True)
class Override:
    field_path: str
    choice: str
    reason: str


@dataclass(frozen=True, slots=True)
class Overrides:
    entries: tuple[Override, ...] = ()


def apply_override(
    overrides: Overrides,
    field_path: str,
    choice: str,
    reason: str,
    *,
    valid_choices: Iterable[str],
    force: bool = False,
) -> Overrides:
    """Record a developer decision for one field.

    Args:
        overrides: the current set of overrides; not mutated.
        field_path: dot-joined path, e.g. "CUSTOMER-RECORD.CUSTOMER-ID".
        choice: the chosen type name (must match a Candidate.type_name).
        reason: why this choice, for the traceability report.
        valid_choices: the field's status=='valid' candidate type names
            (e.g. from `mapping.valid_candidate_names()`, not the
            unfiltered `candidate_names()` - an 'invalid'/'needs-policy'
            candidate is not an acceptable default choice).
        force: skip the valid_choices check.
    Returns:
        Overrides: a new set with this field's override added/replaced -
        the input is never mutated.
    Raises:
        InvalidChoiceError: choice isn't among valid_choices and force
            is False.
    """
    if not force and choice not in valid_choices:
        raise InvalidChoiceError(
            f"{choice!r} is not a valid candidate for {field_path!r}; "
            "pass force=True to override anyway"
        )
    new_entry = Override(field_path=field_path, choice=choice, reason=reason)
    remaining = tuple(e for e in overrides.entries if e.field_path != field_path)
    return Overrides(entries=remaining + (new_entry,))

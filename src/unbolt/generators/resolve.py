"""Combine a MappingReport with Overrides into one type per field.

decision 0004: absent an explicit override, the chosen type is the
first `valid` candidate in the rule's own ladder order - a deterministic
default over an already-enumerated, already-justified list, not a guess.
"""

from unbolt.exceptions import UnapprovedMappingError
from unbolt.mapping.model import MappingReport
from unbolt.overrides import Overrides


def resolve_mapping(report: MappingReport, overrides: Overrides) -> dict[str, str]:
    """Returns {field_path: chosen_type_name} for every field in the report.

    Raises:
        UnapprovedMappingError: a field has no override and no `valid`
            candidate to default to.
    """
    override_by_path = {entry.field_path: entry.choice for entry in overrides.entries}
    resolved: dict[str, str] = {}
    for field in report.fields:
        if field.field_path in override_by_path:
            resolved[field.field_path] = override_by_path[field.field_path]
            continue
        first_valid = next(
            (c.type_name for c in field.candidates if c.status == "valid"), None
        )
        if first_valid is None:
            raise UnapprovedMappingError(
                f"{field.field_path!r} has no valid candidate and no override"
            )
        resolved[field.field_path] = first_valid
    return resolved

"""build_report: field <-> source line <-> rule <-> rationale, in one
place, so answering "why does this field have this type" never means
reading generator code - just this report.
"""

from unbolt.dsl.schema import Dsl
from unbolt.dsl.walk import walk_fields
from unbolt.generators.resolve import resolve_mapping
from unbolt.mapping.model import MappingReport
from unbolt.overrides import Overrides
from unbolt.reporting.model import ConversionReport, TraceEntry
from unbolt.validation.model import ValidationReport


def build_report(
    dsl: Dsl,
    mapping: MappingReport,
    validation: ValidationReport,
    *,
    overrides: Overrides | None = None,
) -> ConversionReport:
    """Raises UnapprovedMappingError (via resolve_mapping) for any field
    with no override and no valid candidate - the same rule generate_code
    enforces, so a report can only describe a conversion that actually
    could have been generated.
    """
    overrides = overrides if overrides is not None else Overrides()
    resolved = resolve_mapping(mapping, overrides)
    source_line_by_path = {path: node.source_line for node, path in walk_fields(dsl)}
    candidates_by_path = {f.field_path: f.candidates for f in mapping.fields}
    override_by_path = {e.field_path: e for e in overrides.entries}

    entries = []
    for field_path, chosen_type in resolved.items():
        candidate = next(
            (c for c in candidates_by_path[field_path] if c.type_name == chosen_type), None
        )
        if candidate is not None:
            rule_id, rationale = candidate.rule_id, candidate.rationale
        else:
            # A forced override whose choice isn't among the field's own
            # candidates (e.g. COMP-1 -> float32) - trace to the
            # developer's own stated reason instead of a rule.
            rule_id, rationale = "override", override_by_path[field_path].reason
        entries.append(
            TraceEntry(
                field_path=field_path,
                source_line=source_line_by_path[field_path],
                chosen_type=chosen_type,
                rule_id=rule_id,
                rationale=rationale,
            )
        )
    entries.sort(key=lambda e: e.field_path)

    return ConversionReport(
        target=mapping.target, entries=tuple(entries), findings=validation.findings
    )

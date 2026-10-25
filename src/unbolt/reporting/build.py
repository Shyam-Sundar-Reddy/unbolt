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
        override = override_by_path.get(field_path)
        if override is not None and candidate is not None and candidate.status != "valid":
            # A forced override onto a candidate the mapping engine itself
            # rejected (e.g. Java double for a decimal field) - trace to
            # the developer's own stated reason, not the rejected
            # candidate's own rationale. Reusing that rationale here would
            # self-contradict: it would name this type as "chosen" while
            # explaining why it was rejected by default.
            rule_id = "override-forced"
            rationale = (
                f"{override.reason} "
                f"(rule engine status: {candidate.status}: {candidate.rationale})"
            )
        elif candidate is not None:
            # No override (resolve_mapping() only ever defaults to a
            # status=='valid' candidate), or an override that happens to
            # match a valid candidate by name.
            rule_id, rationale = candidate.rule_id, candidate.rationale
        else:
            # A forced override whose choice isn't among the field's own
            # candidates at all (e.g. COMP-1 -> float32) - trace to the
            # developer's own stated reason instead of a rule.
            assert override is not None
            rule_id, rationale = "override", override.reason
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

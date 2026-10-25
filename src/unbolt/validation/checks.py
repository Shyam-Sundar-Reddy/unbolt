"""validate_conversion: boundary/precision self-consistency, a
completeness check against the actually-generated text, and one
rolled-up list of every diagnostic (parser + mapping).

The completeness check exists because of two real Phase 3 bugs: a
COMP-1/COMP-2 field silently vanishing from a MappingReport, and a
scalar-root copybook producing no top-level Go type at all. Both were
"a field disappeared and nothing said so" - exactly what this guards
against, now, for every future change to these modules, not just the
two specific bugs already fixed.
"""

from decimal import Decimal

from unbolt.datatypes import describe_datatype
from unbolt.datatypes.sizing import is_alpha_pic, is_edited_pic, is_national_pic
from unbolt.dsl.schema import Dsl
from unbolt.dsl.walk import walk_fields
from unbolt.generators.naming import go_field_name, java_field_name
from unbolt.mapping.model import MappingReport
from unbolt.overrides import Overrides
from unbolt.parser.diagnostics import Diagnostic
from unbolt.validation.model import Finding, ValidationReport


def validate_conversion(
    dsl: Dsl,
    mapping: MappingReport,
    generated: dict[str, str],
    *,
    diagnostics: tuple[Diagnostic, ...] = (),
    overrides: Overrides | None = None,
) -> ValidationReport:
    findings: list[Finding] = []
    generated_text = "\n".join(generated.values())

    findings.extend(_diagnostic_findings(diagnostics))
    findings.extend(_resolved_mapping_findings(mapping, overrides or Overrides()))
    findings.extend(_boundary_and_precision_findings(dsl))
    findings.extend(_completeness_findings(dsl, mapping, generated_text))

    return ValidationReport(findings=tuple(findings))


def _diagnostic_findings(diagnostics: tuple[Diagnostic, ...]) -> list[Finding]:
    return [
        Finding(
            field_path="",
            code=d.code,
            severity=d.severity,
            message=f"line {d.line}: {d.message}",
        )
        for d in diagnostics
    ]


def _resolved_mapping_findings(mapping: MappingReport, overrides: Overrides) -> list[Finding]:
    """Flag either "nothing fits" or "what was actually chosen doesn't fit".

    A field with no override is checked the old way: does *any* candidate
    have status 'valid'? A field with an override is checked against what
    was actually resolved: does the chosen candidate exist and have status
    'valid'? An override can be forced (decision 0004/overrides.py) onto
    an 'invalid' or unlisted candidate - that must surface here, not pass
    silently just because some other, unchosen candidate would have fit.
    """
    override_by_path = {e.field_path: e for e in overrides.entries}
    findings: list[Finding] = []
    for field in mapping.fields:
        override = override_by_path.get(field.field_path)
        if override is None:
            if all(c.status != "valid" for c in field.candidates):
                findings.append(
                    Finding(
                        field_path=field.field_path,
                        code="needs-policy",
                        severity="warning",
                        message="no valid candidate; requires an explicit override",
                    )
                )
            continue
        candidate = next(
            (c for c in field.candidates if c.type_name == override.choice), None
        )
        if candidate is None or candidate.status != "valid":
            status = candidate.status if candidate is not None else "not-a-candidate"
            findings.append(
                Finding(
                    field_path=field.field_path,
                    code="forced-invalid-override",
                    severity="error",
                    message=(
                        f"override chose {override.choice!r} (status: {status}); "
                        f"reason given: {override.reason!r}"
                    ),
                )
            )
    return findings


def _boundary_and_precision_findings(dsl: Dsl) -> list[Finding]:
    findings = []
    for node, field_path in walk_fields(dsl):
        if (
            node.pic is None
            or is_alpha_pic(node.pic)
            or is_edited_pic(node.pic)
            or is_national_pic(node.pic)
        ):
            continue
        facts = describe_datatype(node)
        if facts.min_value > facts.max_value:
            findings.append(
                Finding(field_path, "boundary-inverted", "error", "min_value exceeds max_value")
            )
            continue
        scale_factor = Decimal(10) ** facts.scale
        below_min = facts.min_value - (Decimal(1) / scale_factor)
        above_max = facts.max_value + (Decimal(1) / scale_factor)
        if not (below_min < facts.min_value and above_max > facts.max_value):
            findings.append(
                Finding(
                    field_path,
                    "boundary-off-by-one",
                    "error",
                    "min-1/max+1 did not move outside the range",
                )
            )
        if facts.scale != node.scale:
            findings.append(
                Finding(
                    field_path,
                    "precision-mismatch",
                    "error",
                    "TypeFacts.scale disagrees with FieldNode.scale",
                )
            )
    return findings


def _completeness_findings(dsl: Dsl, mapping: MappingReport, generated_text: str) -> list[Finding]:
    mapped_paths = {f.field_path for f in mapping.fields}
    findings = []
    for node, field_path in walk_fields(dsl):
        if field_path not in mapped_paths:
            continue
        go_name = go_field_name(node.name)
        java_name, _ = java_field_name(node.name, source_line=node.source_line)
        if go_name not in generated_text and java_name not in generated_text:
            findings.append(
                Finding(
                    field_path,
                    "missing-from-output",
                    "error",
                    f"neither {go_name!r} nor {java_name!r} appears in the generated output",
                )
            )
    return findings

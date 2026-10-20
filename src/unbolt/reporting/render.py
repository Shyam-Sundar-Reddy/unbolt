import json
from dataclasses import asdict

from unbolt.reporting.model import ConversionReport


def render_markdown(report: ConversionReport) -> str:
    lines = [f"# Conversion report ({report.target})", ""]

    lines.append("## Fields")
    lines.append("")
    lines.append("| Field | Source line | Chosen type | Rule | Rationale |")
    lines.append("|---|---|---|---|---|")
    for entry in report.entries:
        lines.append(
            f"| `{entry.field_path}` | {entry.source_line} | `{entry.chosen_type}` "
            f"| `{entry.rule_id}` | {entry.rationale} |"
        )

    lines.append("")
    lines.append("## Findings")
    lines.append("")
    if not report.findings:
        lines.append("None.")
    else:
        lines.append("| Field | Code | Severity | Message |")
        lines.append("|---|---|---|---|")
        for finding in report.findings:
            field = f"`{finding.field_path}`" if finding.field_path else "—"
            lines.append(f"| {field} | `{finding.code}` | {finding.severity} | {finding.message} |")

    return "\n".join(lines) + "\n"


def render_json(report: ConversionReport) -> str:
    return json.dumps(asdict(report), sort_keys=True, indent=2) + "\n"

from dataclasses import dataclass

from unbolt.validation.model import Finding


@dataclass(frozen=True, slots=True)
class TraceEntry:
    """One field: where it came from, what it became, and why."""

    field_path: str
    source_line: int
    chosen_type: str
    rule_id: str
    rationale: str


@dataclass(frozen=True, slots=True)
class ConversionReport:
    target: str
    entries: tuple[TraceEntry, ...]
    findings: tuple[Finding, ...]

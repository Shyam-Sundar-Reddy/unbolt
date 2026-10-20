from dataclasses import dataclass
from typing import Literal

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True, slots=True)
class Finding:
    field_path: str
    code: str
    severity: Severity
    message: str


@dataclass(frozen=True, slots=True)
class ValidationReport:
    findings: tuple[Finding, ...]

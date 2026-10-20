"""Stable diagnostic codes. Unsupported syntax is reported, never guessed at.

CBL-Exxx = error (the entry couldn't be parsed at all)
CBL-Wxxx = warning (recognized but unsupported; the entry is dropped)
CBL-Ixxx = info (recognized, parsed, but a detail isn't modeled yet)
"""

from dataclasses import dataclass
from typing import Literal

Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    severity: Severity
    message: str
    line: int


def malformed_entry(line: int, detail: str) -> Diagnostic:
    return Diagnostic("CBL-E001", "error", f"malformed entry: {detail}", line)


def copy_replacing_unsupported(line: int) -> Diagnostic:
    return Diagnostic(
        "CBL-W010", "warning", "COPY ... REPLACING is not supported; entry skipped", line
    )


def renames_unsupported(line: int) -> Diagnostic:
    return Diagnostic(
        "CBL-W020", "warning", "level 66 (RENAMES) is not supported; entry skipped", line
    )


def occurs_depending_on_unsupported(line: int) -> Diagnostic:
    return Diagnostic(
        "CBL-W030",
        "warning",
        "OCCURS ... DEPENDING ON is not supported; treated as not a table",
        line,
    )


def unrecognized_clause(line: int, token: str) -> Diagnostic:
    return Diagnostic("CBL-W040", "warning", f"unrecognized clause token skipped: {token}", line)


def synchronized_not_modeled(line: int) -> Diagnostic:
    return Diagnostic(
        "CBL-I100", "info", "SYNCHRONIZED detected; alignment padding is not modeled", line
    )


def justified_not_modeled(line: int) -> Diagnostic:
    return Diagnostic(
        "CBL-I101", "info", "JUSTIFIED detected; preserved as metadata only", line
    )


def java_reserved_word_renamed(line: int, original: str, renamed: str) -> Diagnostic:
    return Diagnostic(
        "CBL-I102",
        "info",
        f"{original!r} collides with a Java reserved word; renamed to {renamed!r} (decision 0003)",
        line,
    )


# (code, severity, meaning, how to fix) - one row per factory function
# above. docs/diagnostics.md is generated from this, not hand-written
# (tools/gen_diagnostics_doc.py); keep it next to the functions it
# describes so a new diagnostic is hard to add without also cataloging it.
DIAGNOSTIC_CATALOG: tuple[tuple[str, Severity, str, str], ...] = (
    (
        "CBL-E001",
        "error",
        "A data-description entry's level number couldn't be parsed, or "
        "the entry has no name after its level number.",
        "Check the level number and field name on the reported line.",
    ),
    (
        "CBL-W010",
        "warning",
        "COPY ... REPLACING is recognized but not supported; the entry is skipped.",
        "Expand the COPY member by hand, or wait for COPY REPLACING "
        "support (goal.md Extended scope).",
    ),
    (
        "CBL-W020",
        "warning",
        "Level 66 (RENAMES) is recognized but not supported; the entry is skipped.",
        "Remove the RENAMES entry, or reference the renamed range directly.",
    ),
    (
        "CBL-W030",
        "warning",
        "OCCURS ... DEPENDING ON is recognized but not supported; the "
        "field is treated as not a table (occurs=None).",
        "Use a fixed OCCURS n instead, or model the maximum size explicitly.",
    ),
    (
        "CBL-W040",
        "warning",
        "A clause token wasn't recognized and was skipped.",
        "Check the clause's spelling/syntax against docs/supported-constructs.md.",
    ),
    (
        "CBL-I100",
        "info",
        "SYNCHRONIZED was detected; alignment padding is not modeled.",
        "No action needed unless exact byte offsets matter for a future record decoder.",
    ),
    (
        "CBL-I101",
        "info",
        "JUSTIFIED was detected; preserved as metadata only, no behavioral effect.",
        "No action needed.",
    ),
    (
        "CBL-I102",
        "info",
        "A generated Java field name collided with a reserved word and "
        "was renamed with a trailing '_' (decision 0003).",
        "No action needed; the renamed identifier is still traceable via this diagnostic.",
    ),
)

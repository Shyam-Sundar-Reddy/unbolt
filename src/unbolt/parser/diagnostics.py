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

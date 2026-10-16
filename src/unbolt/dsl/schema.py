"""DSL v0 shape: immutable source facts parsed from a copybook.

No parsing or (de)serialization logic lives here yet (Phase 1). This is
the agreed-upon shape every later phase builds against — see
docs/dsl-spec.md for what each field means and
docs/acceptance-criteria.md for hand-computed example values.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FieldNode:
    """One COBOL data item: a group (has children) or an elementary item."""

    name: str
    level: int
    pic: str | None
    usage: str
    signed: bool
    sign_separate: bool
    digits: int
    scale: int
    byte_size: int
    occurs: int | None
    redefines: str | None
    value: str | None
    source_line: int
    children: tuple["FieldNode", ...] = ()


@dataclass(frozen=True, slots=True)
class Dsl:
    """A parsed copybook: schema version, source file, and its field tree."""

    version: str
    source_file: str
    roots: tuple[FieldNode, ...]

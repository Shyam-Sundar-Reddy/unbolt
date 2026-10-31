"""Compatibility classification shape (decision 0011). A FieldChange
never represents a verdict by itself - it's one fact ("this path was
added/removed/changed, here's how") that classify_compatibility()
weighs to produce the one overall Compatibility verdict.
"""

from dataclasses import dataclass
from typing import Literal

Compatibility = Literal["FULL", "FORWARD", "BACKWARD", "BREAKING"]
ChangeKind = Literal["added", "removed", "changed"]


@dataclass(frozen=True, slots=True)
class FieldChange:
    field_path: str
    kind: ChangeKind
    detail: str


@dataclass(frozen=True, slots=True)
class CompatibilityResult:
    compatibility: Compatibility
    changes: tuple[FieldChange, ...]

"""DSL v0 shape: immutable source facts parsed from a copybook.

See docs/dsl-spec.md for what each field means and
docs/acceptance-criteria.md for hand-computed example values.
"""

import json
from dataclasses import asdict, dataclass
from typing import Any

from unbolt.exceptions import SchemaVersionError

DSL_VERSION = "2"


@dataclass(frozen=True, slots=True)
class FieldNode:
    """One COBOL data item: a group (has children) or an elementary item."""

    name: str
    level: int
    pic: str | None
    usage: str
    signed: bool
    sign_separate: bool
    sign_leading: bool
    digits: int
    scale: int
    byte_size: int
    occurs: int | None
    redefines: str | None
    value: str | None
    source_line: int
    offset: int
    children: tuple["FieldNode", ...] = ()


@dataclass(frozen=True, slots=True)
class Dsl:
    """A parsed copybook: schema version, source file, and its field tree."""

    version: str
    source_file: str
    roots: tuple[FieldNode, ...]

    def to_json(self) -> str:
        """Stable, sorted, round-trippable serialization."""
        return json.dumps(asdict(self), sort_keys=True, indent=2) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "Dsl":
        data = json.loads(text)
        if data["version"] != DSL_VERSION:
            got = data["version"]
            raise SchemaVersionError(f"expected DSL version {DSL_VERSION!r}, got {got!r}")
        return cls(
            version=data["version"],
            source_file=data["source_file"],
            roots=tuple(_field_from_dict(root) for root in data["roots"]),
        )


def _field_from_dict(data: dict[str, Any]) -> FieldNode:
    return FieldNode(
        name=data["name"],
        level=data["level"],
        pic=data["pic"],
        usage=data["usage"],
        signed=data["signed"],
        sign_separate=data["sign_separate"],
        sign_leading=data["sign_leading"],
        digits=data["digits"],
        scale=data["scale"],
        byte_size=data["byte_size"],
        occurs=data["occurs"],
        redefines=data["redefines"],
        value=data["value"],
        source_line=data["source_line"],
        offset=data["offset"],
        children=tuple(_field_from_dict(c) for c in data["children"]),
    )

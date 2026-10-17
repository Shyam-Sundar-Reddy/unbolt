"""Raw AST: what the tokens say, before any byte-size math happens."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class AstNode:
    name: str
    level: int
    pic: str | None
    usage: str
    occurs: int | None
    redefines: str | None
    sign_separate: bool
    source_line: int
    children: list["AstNode"] = field(default_factory=list)

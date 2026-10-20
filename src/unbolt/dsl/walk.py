"""The one place that computes a field's dot-joined path from the DSL
root - mapping/engine.py, validation/checks.py, and reporting/build.py
all need the exact same convention, so it lives here once.
"""

from unbolt.dsl.schema import Dsl, FieldNode


def walk_fields(dsl: Dsl) -> list[tuple[FieldNode, str]]:
    """Every node in the tree paired with its dot-joined field_path."""
    out: list[tuple[FieldNode, str]] = []

    def go(node: FieldNode, path: str) -> None:
        field_path = f"{path}.{node.name}" if path else node.name
        out.append((node, field_path))
        for child in node.children:
            go(child, field_path)

    for root in dsl.roots:
        go(root, "")
    return out

"""The one place that computes a field's dot-joined path from a root -
mapping/engine.py, validation/checks.py, reporting/build.py, and
variants/compat.py all need the exact same convention, so it lives
here once.
"""

from unbolt.dsl.schema import Dsl, FieldNode


def walk_from(root: FieldNode) -> list[tuple[FieldNode, str]]:
    """Every node under one root, paired with its dot-joined field_path.

    Unlike walk_fields(), this takes a single FieldNode (e.g. one of
    Dsl.roots, or a root being compared across two separate Dsl
    snapshots) rather than a whole Dsl.
    """
    out: list[tuple[FieldNode, str]] = []

    def go(node: FieldNode, path: str) -> None:
        field_path = f"{path}.{node.name}" if path else node.name
        out.append((node, field_path))
        for child in node.children:
            go(child, field_path)

    go(root, "")
    return out


def walk_fields(dsl: Dsl) -> list[tuple[FieldNode, str]]:
    """Every node in the tree paired with its dot-joined field_path."""
    return [pair for root in dsl.roots for pair in walk_from(root)]

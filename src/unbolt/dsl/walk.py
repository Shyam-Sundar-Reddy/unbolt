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


def fields_named(dsl: Dsl, name: str) -> list[FieldNode]:
    """Every node anywhere in `dsl` whose own (undotted) name matches -
    0, 1, or more than 1 (an ambiguity for the caller to decide about,
    never silently resolved here by picking one)."""
    return [node for node, _ in walk_fields(dsl) if node.name == name]

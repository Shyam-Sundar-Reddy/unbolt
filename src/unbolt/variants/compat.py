"""classify_compatibility: FULL/FORWARD/BACKWARD/BREAKING for two
versions of the same record (decision 0011). Pure function, no I/O -
compares two already-built FieldNode roots, the same roots
decode_record() and recommend_mappings() already consume.
"""

from unbolt.dsl.schema import FieldNode
from unbolt.dsl.walk import walk_from
from unbolt.variants.model import Compatibility, CompatibilityResult, FieldChange

_SIGNATURE_FIELDS = (
    "offset",
    "byte_size",
    "pic",
    "usage",
    "signed",
    "scale",
    "sign_separate",
    "sign_leading",
    "occurs",
)
_GROUP_SIGNATURE_FIELDS = ("offset", "occurs")


def classify_compatibility(old: FieldNode, new: FieldNode) -> CompatibilityResult:
    """Classify how `new` differs from `old` (decision 0011).

    Args: old (FieldNode): the earlier version's root.
        new (FieldNode): the later version's root.
    Returns: CompatibilityResult: FULL if identical; FORWARD if the only
        difference is one or more fields added purely at the end;
        BACKWARD if the only difference is one or more fields removed
        purely at the end; BREAKING otherwise (any in-place change to a
        shared field - including reordering, which always shifts an
        offset - or any non-trailing add/remove, or a mix of trailing
        adds and trailing removes together).
    Example:
        >>> from unbolt.dsl import build_dsl
        >>> from unbolt.parser import parse_copybook
        >>> old = build_dsl(parse_copybook("01 X.\\n  05 A PIC 9(3)."), source_file="<a>").roots[0]
        >>> new = build_dsl(
        ...     parse_copybook("01 X.\\n  05 A PIC 9(3).\\n  05 B PIC 9(2)."), source_file="<b>"
        ... ).roots[0]
        >>> classify_compatibility(old, new).compatibility
        'FORWARD'
    """
    old_by_path = {path: node for node, path in walk_from(old)}
    new_by_path = {path: node for node, path in walk_from(new)}

    removed_paths = old_by_path.keys() - new_by_path.keys()
    added_paths = new_by_path.keys() - old_by_path.keys()
    common_paths = old_by_path.keys() & new_by_path.keys()
    changed_paths = {
        p for p in common_paths if _signature(old_by_path[p]) != _signature(new_by_path[p])
    }

    changes = (
        [
            FieldChange(p, "removed", _describe_removed(old_by_path[p]))
            for p in sorted(removed_paths)
        ]
        + [FieldChange(p, "added", _describe_added(new_by_path[p])) for p in sorted(added_paths)]
        + [
            FieldChange(p, "changed", _describe_changed(old_by_path[p], new_by_path[p]))
            for p in sorted(changed_paths)
        ]
    )

    compatibility = _classify(
        old_byte_size=old.byte_size,
        new_byte_size=new.byte_size,
        added=added_paths,
        removed=removed_paths,
        changed=changed_paths,
        new_by_path=new_by_path,
        old_by_path=old_by_path,
    )
    return CompatibilityResult(compatibility=compatibility, changes=tuple(changes))


def _classify(
    *,
    old_byte_size: int,
    new_byte_size: int,
    added: set[str],
    removed: set[str],
    changed: set[str],
    new_by_path: dict[str, FieldNode],
    old_by_path: dict[str, FieldNode],
) -> Compatibility:
    if not added and not removed and not changed:
        return "FULL"
    if changed:
        return "BREAKING"

    all_added_trailing = all(new_by_path[p].offset >= old_byte_size for p in added)
    all_removed_trailing = all(old_by_path[p].offset >= new_byte_size for p in removed)

    if added and not removed and all_added_trailing:
        return "FORWARD"
    if removed and not added and all_removed_trailing:
        return "BACKWARD"
    return "BREAKING"


def _is_group(node: FieldNode) -> bool:
    return node.pic is None and bool(node.children)


def _signature_fields(node: FieldNode) -> tuple[str, ...]:
    # A group's byte_size (and pic/usage/signed/scale/sign_*) is derived
    # entirely from its children - comparing it here would double-count
    # a child's own added/removed/changed signal as a second, spurious
    # "the group itself changed" signal. Only offset/occurs are facts
    # about the group itself.
    return _GROUP_SIGNATURE_FIELDS if _is_group(node) else _SIGNATURE_FIELDS


def _signature(node: FieldNode) -> tuple[object, ...]:
    return tuple(getattr(node, name) for name in _signature_fields(node))


def _describe_added(node: FieldNode) -> str:
    return f"added at offset {node.offset}, {node.byte_size} bytes"


def _describe_removed(node: FieldNode) -> str:
    return f"removed from offset {node.offset}, was {node.byte_size} bytes"


def _describe_changed(old: FieldNode, new: FieldNode) -> str:
    # The union of both sides' relevant fields - if a field flips from a
    # group to an elementary item (or back) between versions, its
    # signature field sets differ too, and every difference should
    # still show up in the description.
    fields = dict.fromkeys(_signature_fields(old) + _signature_fields(new))
    diffs = [
        f"{name} {getattr(old, name)!r} -> {getattr(new, name)!r}"
        for name in fields
        if getattr(old, name) != getattr(new, name)
    ]
    return "; ".join(diffs)

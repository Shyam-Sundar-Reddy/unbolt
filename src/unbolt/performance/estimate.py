"""estimate_storage: theoretical per-record size, labeled "estimated"
(goal.md section 4/12: estimates and measurements are never mixed).

The COBOL side comes straight from FieldNode.byte_size - already exact,
computed in Phase 1 from PIC/USAGE rules. The target side is only given
for fixed-size types; a variable/heap-allocated type (big.Int,
BigInteger, BigDecimal) gets target_bytes=None rather than a guessed
number. An alphanumeric field's target_bytes uses its own COBOL length
(PIC X(n) is a fixed, known length) - that's a stated assumption, not a
precise one: it doesn't count a Go string header or Java String object
overhead, only the character content.
"""

from unbolt.datatypes.sizing import is_alpha_pic, is_edited_pic, is_national_pic
from unbolt.dsl.schema import Dsl, FieldNode
from unbolt.generators.resolve import resolve_mapping
from unbolt.mapping.model import MappingReport
from unbolt.overrides import Overrides
from unbolt.performance.model import Estimate, FieldSizeEstimate

_FIXED_TARGET_BYTES = {
    "int8": 1, "int16": 2, "int32": 4, "int64": 8,
    "uint8": 1, "uint16": 2, "uint32": 4, "uint64": 8,
    "byte": 1, "short": 2, "int": 4, "long": 8,
    "float32": 4, "float64": 8, "float": 4, "double": 8,
    "int64 (scaled)": 8,
}
_STRING_TYPE = {"go": "string", "java": "String"}


def estimate_storage(
    dsl: Dsl, mapping: MappingReport, *, overrides: Overrides | None = None
) -> tuple[Estimate, ...]:
    """One Estimate per DSL root (a copybook can declare more than one
    01-level record).

    Raises:
        UnapprovedMappingError: a mapped field has no override and no
            valid candidate (propagated from resolve_mapping).
    """
    resolved = resolve_mapping(mapping, overrides if overrides is not None else Overrides())
    string_type = _STRING_TYPE[mapping.target]

    return tuple(
        _estimate_root(root, resolved, string_type, mapping.target) for root in dsl.roots
    )


def _estimate_root(
    root: FieldNode, resolved: dict[str, str], string_type: str, target: str
) -> Estimate:
    fields: list[FieldSizeEstimate] = []
    totals = _RunningTotal()

    def visit(node: FieldNode, path: str, multiplier: int) -> None:
        # Each FieldSizeEstimate reports one occurrence's own size - same
        # convention as FieldNode.byte_size (Phase 1). `multiplier` is the
        # accumulated OCCURS count from every ancestor, applied only when
        # rolling into the record-level total, not into the per-field entry.
        effective = multiplier * (node.occurs or 1)
        if node.pic is None and node.children:
            for child in node.children:
                visit(child, f"{path}.{child.name}", effective)
            return
        if node.pic is not None and (
            is_alpha_pic(node.pic) or is_edited_pic(node.pic) or is_national_pic(node.pic)
        ):
            # Edited (CBL-W050) and national/DBCS (CBL-W060) pictures are
            # text width, same as alpha - without this, such a leaf
            # matches none of these branches and silently contributes 0.
            fields.append(FieldSizeEstimate(path, node.byte_size, string_type, node.byte_size))
            totals.add(node.byte_size * effective)
            return
        if path in resolved:
            chosen = resolved[path]
            target_bytes = _FIXED_TARGET_BYTES.get(chosen)
            fields.append(FieldSizeEstimate(path, node.byte_size, chosen, target_bytes))
            if target_bytes is None:
                totals.mark_unknown()
            else:
                totals.add(target_bytes * effective)

    visit(root, root.name, 1)

    return Estimate(
        label="estimated",
        target=target,
        root_name=root.name,
        cobol_record_bytes=root.byte_size,
        target_record_bytes=totals.value,
        fields=tuple(fields),
    )


class _RunningTotal:
    """Sums bytes, except once any part is unknown the total stays
    unknown (never silently treated as zero)."""

    def __init__(self) -> None:
        self.value: int | None = 0

    def add(self, amount: int) -> None:
        if self.value is not None:
            self.value += amount

    def mark_unknown(self) -> None:
        self.value = None

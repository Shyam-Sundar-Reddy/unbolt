from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FieldSizeEstimate:
    field_path: str
    cobol_bytes: int
    target_type: str
    target_bytes: int | None
    """None means variable/heap-allocated (big.Int, BigInteger, BigDecimal,
    string content) - never guessed as a fixed number."""


@dataclass(frozen=True, slots=True)
class Estimate:
    """Theoretical per-record size. Always "estimated" - see
    docs/performance.md for how this differs from a measured number.
    """

    label: str
    target: str
    root_name: str
    cobol_record_bytes: int
    target_record_bytes: int | None
    """None if any field's target_bytes is variable-size - never summed
    as if an unknown size were zero."""
    fields: tuple[FieldSizeEstimate, ...]

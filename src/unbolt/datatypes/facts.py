from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TypeFacts:
    """Computed range facts for one elementary field, under a chosen dialect/TRUNC."""

    signed: bool
    digits: int
    scale: int
    byte_size: int
    min_value: Decimal
    max_value: Decimal

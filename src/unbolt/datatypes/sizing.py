"""PIC/USAGE -> digits, scale, byte size, range. The single source of truth
for this math; the parser's build_dsl step and describe_datatype() both
call into this module instead of each re-implementing it.

Dialect: IBM Enterprise COBOL. TRUNC: STD (PIC-limited range), except
COMP-5, which IBM documents as always using the full native binary range
regardless of TRUNC - see docs/decisions/0001-dialect-charset-trunc-targets.md.
"""

import re
from decimal import Decimal
from typing import TYPE_CHECKING

from unbolt.datatypes.facts import TypeFacts
from unbolt.exceptions import UnsupportedPictureError

if TYPE_CHECKING:
    from unbolt.dsl.schema import FieldNode

_PIC_RUN = re.compile(r"([9AX])(\((\d+)\))?")

_PACKED_USAGES = {"COMP-3", "PACKED-DECIMAL"}
_BINARY_TIER_USAGES = {"COMP", "COMP-4", "BINARY", "COMP-5"}


def is_signed(pic: str) -> bool:
    return pic.upper().startswith("S")


def is_alpha_pic(pic: str) -> bool:
    upper = pic.upper()
    return "9" not in upper and ("X" in upper or "A" in upper)


def parse_pic_digits_scale(pic: str) -> tuple[int, int]:
    """Total digit count and scale (fractional digits) from a numeric PIC."""
    body = pic.upper()
    if body.startswith("S"):
        body = body[1:]
    integer_part, _, fraction_part = body.partition("V")
    integer_digits = _count_symbol(integer_part, "9")
    fraction_digits = _count_symbol(fraction_part, "9")
    return integer_digits + fraction_digits, fraction_digits


def alpha_byte_size(pic: str) -> int:
    upper = pic.upper()
    return _count_symbol(upper, "X") + _count_symbol(upper, "A")


def _count_symbol(segment: str, symbol: str) -> int:
    total = 0
    for match in _PIC_RUN.finditer(segment):
        if match.group(1) == symbol:
            total += int(match.group(3)) if match.group(3) else 1
    return total


def numeric_byte_size(usage: str, digits: int, sign_separate: bool) -> int:
    usage_norm = usage.upper()
    if usage_norm == "DISPLAY":
        return digits + (1 if sign_separate else 0)
    if usage_norm in _PACKED_USAGES:
        return digits // 2 + 1
    if usage_norm in _BINARY_TIER_USAGES:
        return _binary_tier_bytes(digits)
    if usage_norm == "COMP-1":
        return 4
    if usage_norm == "COMP-2":
        return 8
    raise UnsupportedPictureError(f"unknown USAGE {usage!r}")


def _binary_tier_bytes(digits: int) -> int:
    if digits <= 4:
        return 2
    if digits <= 9:
        return 4
    if digits <= 18:
        return 8
    raise UnsupportedPictureError(f"{digits} digits exceeds the 18-digit BINARY/COMP limit")


def numeric_range(
    signed: bool, digits: int, scale: int, usage: str, byte_size: int
) -> tuple[Decimal, Decimal]:
    """Min/max under TRUNC(STD), except COMP-5 which uses the full binary range."""
    if usage.upper() == "COMP-5":
        bits = byte_size * 8
        unscaled_max = 2 ** (bits - 1) - 1 if signed else 2**bits - 1
        unscaled_min = -(2 ** (bits - 1)) if signed else 0
    else:
        unscaled_max = 10**digits - 1
        unscaled_min = -unscaled_max if signed else 0
    scale_factor = Decimal(10) ** scale
    return Decimal(unscaled_min) / scale_factor, Decimal(unscaled_max) / scale_factor


def describe_datatype(field: "FieldNode") -> TypeFacts:
    """Compute min/max for an elementary field already sized by build_dsl.

    Raises:
        UnsupportedPictureError: field is a group or an alphanumeric item -
            neither has a numeric range.
    """
    if field.pic is None or is_alpha_pic(field.pic):
        raise UnsupportedPictureError(
            f"{field.name}: no numeric range for a group/alphanumeric field"
        )
    min_value, max_value = numeric_range(
        field.signed, field.digits, field.scale, field.usage, field.byte_size
    )
    return TypeFacts(
        signed=field.signed,
        digits=field.digits,
        scale=field.scale,
        byte_size=field.byte_size,
        min_value=min_value,
        max_value=max_value,
    )

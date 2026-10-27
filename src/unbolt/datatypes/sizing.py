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
_EDITED_PIC_RUN = re.compile(r"([9AXZ*$,.+\-])(\((\d+)\))?")
_EDITED_PIC_CHARS = set("Z*$,.+-")
_NATIONAL_PIC_RUN = re.compile(r"([NG])(\((\d+)\))?")
_NATIONAL_PIC_CHARS = set("NG")

_PACKED_USAGES = {"COMP-3", "PACKED-DECIMAL"}
_BINARY_TIER_USAGES = {"COMP", "COMP-4", "BINARY", "COMP-5"}


def is_signed(pic: str) -> bool:
    return pic.upper().startswith("S")


def is_packed_usage(usage: str) -> bool:
    """COMP-3/PACKED-DECIMAL: two digits per byte, sign in the last nibble."""
    return usage.upper() in _PACKED_USAGES


def is_alpha_pic(pic: str) -> bool:
    upper = pic.upper()
    return "9" not in upper and ("X" in upper or "A" in upper)


def is_edited_pic(pic: str) -> bool:
    """Display-formatting symbols (Z, *, $, comma, decimal point, +/-,
    CR/DB) - these describe how a value is *shown*, not its value or
    storage the way 9/V/S do. Treated as text width, never as digits -
    silently counting them as '9' would produce a wrong digit count.
    """
    upper = pic.upper()
    return any(ch in upper for ch in _EDITED_PIC_CHARS) or "CR" in upper or "DB" in upper


def edited_pic_width(pic: str) -> int:
    """Approximate displayed character width. Exact for the common
    patterns (Z/9/*/comma/period runs); CR/DB each add 2 for their
    fixed two-character suffix. Floating currency/sign strings
    (`$$$,$$9.99`) aren't given special-cased narrower counting -
    every symbol occurrence just counts as one position, which is
    always a safe upper bound, never an undercount.
    """
    upper = pic.upper()
    width = sum(
        int(match.group(3)) if match.group(3) else 1 for match in _EDITED_PIC_RUN.finditer(upper)
    )
    width += 2 * upper.count("CR") + 2 * upper.count("DB")
    return width


def is_national_pic(pic: str) -> bool:
    """`PIC N`/`PIC G` (national/DBCS) - no DBCS codec exists, so these
    are recognized and sized as double-byte text width, never decoded.
    """
    upper = pic.upper()
    return any(ch in upper for ch in _NATIONAL_PIC_CHARS)


def national_pic_width(pic: str) -> int:
    """Byte width of a national/DBCS picture: 2 bytes per character
    (goal.md §5.5) - storage width only, never a decoded value.
    """
    upper = pic.upper()
    return 2 * sum(
        int(match.group(3)) if match.group(3) else 1
        for match in _NATIONAL_PIC_RUN.finditer(upper)
    )


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
        UnsupportedPictureError: field is a group, alphanumeric, an
            edited picture, or a national/DBCS picture - none has a
            numeric range.
    """
    if (
        field.pic is None
        or is_alpha_pic(field.pic)
        or is_edited_pic(field.pic)
        or is_national_pic(field.pic)
    ):
        raise UnsupportedPictureError(
            f"{field.name}: no numeric range for a group/alphanumeric/"
            "edited-picture/national-picture field"
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

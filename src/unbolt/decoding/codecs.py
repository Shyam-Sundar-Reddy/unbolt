"""Byte-level decode for DISPLAY (zoned decimal) fields (decision 0010:
cp037 default EBCDIC code page, explicit override allowed). Only DISPLAY
is implemented in this slice - COMP-3/binary decode, SIGN IS SEPARATE,
and OCCURS/REDEFINES-aware decode are later Phase 8 slices (phase.md).

Sign overpunch is a byte-value convention, not a text decode: the last
digit byte's zone nibble (high 4 bits) carries the sign (0xC = positive,
0xD = negative, 0xF = unsigned/positive) and its digit nibble (low 4
bits) carries that digit's value directly - cp037's own character
mapping for those byte values (e.g. 0xC1 -> 'A') is irrelevant here and
is never consulted for the sign byte.
"""

from decimal import Decimal

from unbolt.exceptions import InvalidSignNibbleError, UnsupportedDecodeError

DEFAULT_CODEPAGE = "cp037"

_POSITIVE_ZONE = 0xC0
_NEGATIVE_ZONE = 0xD0
_UNSIGNED_ZONE = 0xF0


def decode_display(
    raw: bytes,
    *,
    signed: bool,
    sign_separate: bool,
    scale: int,
    codepage: str = DEFAULT_CODEPAGE,
) -> Decimal:
    """Decode a DISPLAY (zoned decimal) field's raw bytes to its value.

    Args: raw (bytes): the field's own bytes, length == its byte_size.
        signed (bool): whether the PIC has S.
        sign_separate (bool): SIGN IS SEPARATE present.
        scale (int): fractional digit count (the V position).
        codepage (str): EBCDIC code page; cp037 by default (decision 0010).
    Returns: Decimal: the decoded value, already divided by 10**scale.
    Raises:
        UnsupportedDecodeError: sign_separate is True - leading/trailing
            position isn't tracked anywhere in the DSL (parser.py parses
            but discards it), so decoding it correctly isn't possible
            without guessing a placement.
        InvalidSignNibbleError: a signed field's last byte's zone nibble
            isn't a recognized overpunch sign, or a byte decodes to a
            non-digit character where a digit was expected.
    Example:
        >>> decode_display(bytes([0xF1, 0xF2, 0xC3]), signed=True, sign_separate=False, scale=0)
        Decimal('123')
    """
    if sign_separate:
        raise UnsupportedDecodeError(
            "SIGN IS SEPARATE decode isn't supported yet - leading/trailing "
            "position isn't tracked in the DSL (parser.py discards it)"
        )
    if not raw:
        raise InvalidSignNibbleError("empty DISPLAY field has no digit bytes to decode")

    if not signed:
        text = raw.decode(codepage)
        if not text.isdigit():
            raise InvalidSignNibbleError(f"non-digit byte(s) in unsigned DISPLAY field: {text!r}")
        return Decimal(int(text)) / (Decimal(10) ** scale)

    *lead, last = raw
    lead_text = bytes(lead).decode(codepage)
    if lead_text and not lead_text.isdigit():
        raise InvalidSignNibbleError(f"non-digit byte(s) in signed DISPLAY field: {lead_text!r}")

    zone, digit = last & 0xF0, last & 0x0F
    if zone in (_POSITIVE_ZONE, _UNSIGNED_ZONE):
        sign = 1
    elif zone == _NEGATIVE_ZONE:
        sign = -1
    else:
        raise InvalidSignNibbleError(
            f"last byte {last:#04x} has an unrecognized sign nibble {zone:#04x}"
        )
    if digit > 9:
        raise InvalidSignNibbleError(f"last byte {last:#04x} has a non-digit value nibble {digit}")

    unscaled = int(lead_text + str(digit)) if lead_text else digit
    return Decimal(sign * unscaled) / (Decimal(10) ** scale)

"""Byte-level decode for DISPLAY (zoned decimal), COMP-3/PACKED-DECIMAL,
and COMP/COMP-4/COMP-5/BINARY fields (decision 0010: cp037 default
EBCDIC code page, explicit override allowed - charset only matters for
DISPLAY's text/overpunch decode, binary is just bytes). COMP-1/COMP-2
(float), SIGN IS SEPARATE, and OCCURS/REDEFINES-aware decode are later
Phase 8 slices (phase.md).

Sign overpunch is a byte-value convention, not a text decode: the last
digit byte's zone nibble (high 4 bits) carries the sign (0xC = positive,
0xD = negative, 0xF = unsigned/positive) and its digit nibble (low 4
bits) carries that digit's value directly - cp037's own character
mapping for those byte values (e.g. 0xC1 -> 'A') is irrelevant here and
is never consulted for the sign byte. Packed decimal uses the same C/D/F
sign convention, but as a whole nibble on its own (not combined with a
digit) - the field's very last nibble, after every other nibble has
already been read as a plain digit.
"""

from decimal import Decimal

from unbolt.exceptions import InvalidSignNibbleError, UnsupportedDecodeError

DEFAULT_CODEPAGE = "cp037"

_POSITIVE_ZONE = 0xC0
_NEGATIVE_ZONE = 0xD0
_UNSIGNED_ZONE = 0xF0

_POSITIVE_SIGN_NIBBLES = (0xC, 0xF)
_NEGATIVE_SIGN_NIBBLE = 0xD


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


def decode_packed(raw: bytes, *, digits: int, scale: int) -> Decimal:
    """Decode a COMP-3/PACKED-DECIMAL field's raw bytes to its value.

    Args: raw (bytes): the field's own bytes, length == its byte_size
            (datatypes.sizing.numeric_byte_size's digits // 2 + 1).
        digits (int): total digit count. When even, the encoding has one
            leading zero nibble before the real digits start - standard
            packed-decimal padding, not a choice made here.
        scale (int): fractional digit count (the V position).
    Returns: Decimal: the decoded value, already divided by 10**scale.
    Raises:
        InvalidSignNibbleError: the last nibble isn't a recognized sign,
            a leading pad nibble isn't zero, or a digit nibble isn't 0-9.
    Example:
        >>> decode_packed(bytes([0x12, 0x3C]), digits=3, scale=0)
        Decimal('123')
    """
    nibbles = [n for byte in raw for n in (byte >> 4, byte & 0x0F)]
    *digit_nibbles, sign_nibble = nibbles

    pad = len(digit_nibbles) - digits
    if any(n != 0 for n in digit_nibbles[:pad]):
        raise InvalidSignNibbleError(
            f"packed decimal has a non-zero leading pad nibble: {digit_nibbles[:pad]}"
        )
    real_digits = digit_nibbles[pad:]
    if any(n > 9 for n in real_digits):
        raise InvalidSignNibbleError(f"packed decimal has a non-digit nibble in {real_digits}")

    if sign_nibble in _POSITIVE_SIGN_NIBBLES:
        sign = 1
    elif sign_nibble == _NEGATIVE_SIGN_NIBBLE:
        sign = -1
    else:
        raise InvalidSignNibbleError(
            f"packed decimal has an unrecognized sign nibble {sign_nibble:#x}"
        )

    unscaled = int("".join(str(n) for n in real_digits)) if real_digits else 0
    return Decimal(sign * unscaled) / (Decimal(10) ** scale)


def decode_binary(raw: bytes, *, signed: bool, scale: int) -> Decimal:
    """Decode a COMP/COMP-4/COMP-5/BINARY field's raw bytes to its value.

    Mechanically identical for all four usages - decision 0001's COMP-5
    exception (full native binary range vs. TRUNC(STD)'s PIC-limited
    range) is a range/validation policy (Phase 2's datatypes/mapping),
    not a byte-decode difference; every one of them is a plain
    big-endian two's-complement (signed) or unsigned integer.

    Args: raw (bytes): the field's own bytes - 2/4/8 (halfword/fullword/
            doubleword, by digit count).
        signed (bool): whether the PIC has S.
        scale (int): fractional digit count (the V position).
    Returns: Decimal: the decoded value, already divided by 10**scale.
    Example:
        >>> decode_binary(bytes([0x00, 0x7B]), signed=False, scale=0)
        Decimal('123')
    """
    unscaled = int.from_bytes(raw, byteorder="big", signed=signed)
    return Decimal(unscaled) / (Decimal(10) ** scale)

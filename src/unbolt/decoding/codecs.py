"""Byte-level decode for DISPLAY (zoned decimal), COMP-3/PACKED-DECIMAL,
and COMP/COMP-4/COMP-5/BINARY fields (decision 0010: cp037 default
EBCDIC code page, explicit override allowed - charset only matters for
DISPLAY's text/overpunch decode, binary is just bytes). COMP-1/COMP-2
(float) and OCCURS/REDEFINES-aware decode are later Phase 8 slices
(phase.md).

Sign overpunch is a byte-value convention, not a text decode: the
overpunched digit byte's zone nibble (high 4 bits) carries the sign
(0xC = positive, 0xD = negative, 0xF = unsigned/positive) and its digit
nibble (low 4 bits) carries that digit's value directly - cp037's own
character mapping for that byte value (e.g. 0xC1 -> 'A') is irrelevant
here and is never consulted. SIGN IS SEPARATE is the opposite: the sign
byte is a plain '+'/'-' character, decoded normally through the
codepage like any other text. SIGN IS LEADING (either form) puts the
sign at the start of the field instead of the end - COBOL's default
without a SIGN clause is trailing, non-separate (overpunch). Packed
decimal uses the same C/D/F sign convention as overpunch, but as a
whole nibble on its own (not combined with a digit) - the field's very
last nibble, after every other nibble has already been read as a plain
digit.
"""

from decimal import Decimal

from unbolt.exceptions import InvalidSignNibbleError

DEFAULT_CODEPAGE = "cp037"

_POSITIVE_ZONE = 0xC0
_NEGATIVE_ZONE = 0xD0
_UNSIGNED_ZONE = 0xF0

_POSITIVE_SIGN_NIBBLES = (0xC, 0xF)
_NEGATIVE_SIGN_NIBBLE = 0xD


def _overpunch_sign_and_digit(byte: int) -> tuple[int, int]:
    zone, digit = byte & 0xF0, byte & 0x0F
    if zone in (_POSITIVE_ZONE, _UNSIGNED_ZONE):
        sign = 1
    elif zone == _NEGATIVE_ZONE:
        sign = -1
    else:
        raise InvalidSignNibbleError(
            f"byte {byte:#04x} has an unrecognized sign nibble {zone:#04x}"
        )
    if digit > 9:
        raise InvalidSignNibbleError(f"byte {byte:#04x} has a non-digit value nibble {digit}")
    return sign, digit


def decode_display(
    raw: bytes,
    *,
    signed: bool,
    sign_separate: bool,
    sign_leading: bool = False,
    scale: int,
    codepage: str = DEFAULT_CODEPAGE,
) -> Decimal:
    """Decode a DISPLAY (zoned decimal) field's raw bytes to its value.

    Args: raw (bytes): the field's own bytes, length == its byte_size.
        signed (bool): whether the PIC has S.
        sign_separate (bool): SIGN IS SEPARATE present (a plain '+'/'-'
            byte, not overpunched).
        sign_leading (bool): SIGN IS LEADING present - the sign (separate
            or overpunched) is the field's first byte, not its last.
            COBOL's default without a SIGN clause is trailing.
        scale (int): fractional digit count (the V position).
        codepage (str): EBCDIC code page; cp037 by default (decision 0010).
    Returns: Decimal: the decoded value, already divided by 10**scale.
    Raises:
        InvalidSignNibbleError: the sign byte/nibble isn't recognized,
            or a byte decodes to a non-digit character where a digit
            was expected.
    Example:
        >>> decode_display(bytes([0xF1, 0xF2, 0xC3]), signed=True, sign_separate=False, scale=0)
        Decimal('123')
    """
    if not raw:
        raise InvalidSignNibbleError("empty DISPLAY field has no digit bytes to decode")

    if not signed:
        text = raw.decode(codepage)
        if not text.isdigit():
            raise InvalidSignNibbleError(f"non-digit byte(s) in unsigned DISPLAY field: {text!r}")
        return Decimal(int(text)) / (Decimal(10) ** scale)

    if sign_separate:
        sign_byte, digit_bytes = (raw[0], raw[1:]) if sign_leading else (raw[-1], raw[:-1])
        sign_char = bytes([sign_byte]).decode(codepage)
        if sign_char not in ("+", "-"):
            raise InvalidSignNibbleError(
                f"separate sign byte decoded to {sign_char!r}, expected '+' or '-'"
            )
        sign = 1 if sign_char == "+" else -1
        digit_text = digit_bytes.decode(codepage)
        if not digit_text.isdigit():
            raise InvalidSignNibbleError(
                f"non-digit byte(s) in signed DISPLAY field: {digit_text!r}"
            )
        return Decimal(sign * int(digit_text)) / (Decimal(10) ** scale)

    overpunch_byte, rest = (raw[0], raw[1:]) if sign_leading else (raw[-1], raw[:-1])
    rest_text = rest.decode(codepage)
    if rest_text and not rest_text.isdigit():
        raise InvalidSignNibbleError(f"non-digit byte(s) in signed DISPLAY field: {rest_text!r}")
    sign, digit = _overpunch_sign_and_digit(overpunch_byte)
    digit_text = f"{digit}{rest_text}" if sign_leading else f"{rest_text}{digit}"
    return Decimal(sign * int(digit_text)) / (Decimal(10) ** scale)


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

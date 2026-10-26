from decimal import Decimal

import pytest

from unbolt.decoding.codecs import decode_display
from unbolt.exceptions import InvalidSignNibbleError, UnsupportedDecodeError


def test_unsigned_display_decodes_plain_digits() -> None:
    # "007" -> cp037 0xF0 0xF0 0xF7
    value = decode_display(bytes([0xF0, 0xF0, 0xF7]), signed=False, sign_separate=False, scale=0)
    assert value == Decimal("7")


def test_signed_display_positive_overpunch() -> None:
    # "123" positive: lead "12" (0xF1 0xF2) + last digit 3 with positive zone 0xC
    value = decode_display(bytes([0xF1, 0xF2, 0xC3]), signed=True, sign_separate=False, scale=0)
    assert value == Decimal("123")


def test_signed_display_negative_overpunch() -> None:
    # "123" negative: last digit 3 with negative zone 0xD
    value = decode_display(bytes([0xF1, 0xF2, 0xD3]), signed=True, sign_separate=False, scale=0)
    assert value == Decimal("-123")


def test_signed_display_unsigned_zone_on_last_byte_is_treated_as_positive() -> None:
    # A signed field whose value happens to be stored with the plain
    # unsigned zone (0xF) on the last byte is still a valid positive value.
    value = decode_display(bytes([0xF1, 0xF2, 0xF3]), signed=True, sign_separate=False, scale=0)
    assert value == Decimal("123")


def test_scale_divides_the_unscaled_value() -> None:
    # PIC S9(3)V99 value 123.45, positive: unscaled digits "12345"
    value = decode_display(
        bytes([0xF1, 0xF2, 0xF3, 0xF4, 0xC5]), signed=True, sign_separate=False, scale=2
    )
    assert value == Decimal("123.45")


def test_single_byte_signed_field_decodes_from_the_sign_nibble_alone() -> None:
    value = decode_display(bytes([0xD7]), signed=True, sign_separate=False, scale=0)
    assert value == Decimal("-7")


def test_sign_separate_is_not_supported_yet() -> None:
    with pytest.raises(UnsupportedDecodeError, match="SIGN IS SEPARATE"):
        decode_display(bytes([0xF1, 0x2B]), signed=True, sign_separate=True, scale=0)


def test_invalid_sign_nibble_raises_a_clear_error() -> None:
    # 0xA0 zone is neither a positive/negative overpunch nor the plain
    # unsigned zone - must raise, never silently guess a sign.
    with pytest.raises(InvalidSignNibbleError, match="sign nibble"):
        decode_display(bytes([0xF1, 0xA3]), signed=True, sign_separate=False, scale=0)


def test_non_digit_byte_in_unsigned_field_raises() -> None:
    with pytest.raises(InvalidSignNibbleError, match="non-digit"):
        decode_display(bytes([0xC1, 0xF2]), signed=False, sign_separate=False, scale=0)


def test_non_digit_byte_in_signed_fields_leading_digits_raises() -> None:
    with pytest.raises(InvalidSignNibbleError, match="non-digit"):
        decode_display(bytes([0xC1, 0xC3]), signed=True, sign_separate=False, scale=0)


def test_empty_bytes_raises() -> None:
    with pytest.raises(InvalidSignNibbleError, match="empty"):
        decode_display(b"", signed=False, sign_separate=False, scale=0)

"""decode_rdw_record() acceptance tests: a real fixture's bytes wrapped
in a correct RDW header must decode identically to calling
decode_record() directly on the unwrapped bytes - RDW framing is
additive, it changes nothing about how the payload itself is decoded.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from unbolt.decoding import decode_rdw_record, decode_record
from unbolt.dsl import build_dsl
from unbolt.exceptions import RdwHeaderError, RecordLengthMismatchError
from unbolt.parser import parse_copybook

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _root(name: str):
    source = (FIXTURES_DIR / f"{name}.cpy").read_text()
    dsl = build_dsl(parse_copybook(source), source_file=f"{name}.cpy")
    return dsl.roots[0]


def _rdw(record_bytes: bytes, *, reserved: bytes = b"\x00\x00") -> bytes:
    total_length = len(record_bytes) + 4
    return total_length.to_bytes(2, "big") + reserved + record_bytes


def test_rdw_wrapped_record_decodes_identically_to_the_plain_record() -> None:
    root = _root("flat_display")
    record_bytes = bytes(
        [0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6]  # CUSTOMER-ID "123456"
        + [0xF0, 0xF4, 0xD5]  # CUSTOMER-AGE "045" negative
        + [0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xC9]  # ACCOUNT-BALANCE +123456789
    )

    plain = decode_record(root, record_bytes)
    rdw_wrapped = decode_rdw_record(root, _rdw(record_bytes))

    assert rdw_wrapped == plain == {
        "CUSTOMER-RECORD.CUSTOMER-ID": Decimal("123456"),
        "CUSTOMER-RECORD.CUSTOMER-AGE": Decimal("-45"),
        "CUSTOMER-RECORD.ACCOUNT-BALANCE": Decimal("1234567.89"),
    }


def test_rdw_ignores_trailing_bytes_from_a_following_record() -> None:
    root = _root("flat_display")
    record_bytes = bytes([0xF0] * 18)  # every field decodes to 0
    next_record_marker = b"\xAB\xCD\xEF"  # garbage that must never be touched

    values = decode_rdw_record(root, _rdw(record_bytes) + next_record_marker)

    assert values == {
        "CUSTOMER-RECORD.CUSTOMER-ID": Decimal("0"),
        "CUSTOMER-RECORD.CUSTOMER-AGE": Decimal("0"),
        "CUSTOMER-RECORD.ACCOUNT-BALANCE": Decimal("0"),
    }


def test_rdw_header_too_short_raises() -> None:
    root = _root("flat_display")
    with pytest.raises(RdwHeaderError, match="needs 4 bytes"):
        decode_rdw_record(root, b"\x00\x16\x00")


def test_rdw_declared_length_past_end_of_buffer_raises() -> None:
    root = _root("flat_display")
    header = (100).to_bytes(2, "big") + b"\x00\x00"  # declares 100 bytes total
    with pytest.raises(RdwHeaderError, match="only 10 are available"):
        decode_rdw_record(root, header + bytes(6))  # 4-byte header + 6 bytes = 10 total


def test_rdw_declared_length_below_header_size_raises() -> None:
    root = _root("flat_display")
    header = (2).to_bytes(2, "big") + b"\x00\x00"  # declares less than the header itself
    with pytest.raises(RdwHeaderError, match="below its own 4-byte header"):
        decode_rdw_record(root, header + bytes(20))


def test_rdw_nonzero_reserved_bytes_raises() -> None:
    root = _root("flat_display")
    with pytest.raises(RdwHeaderError, match="spanned records"):
        decode_rdw_record(root, _rdw(bytes(18), reserved=b"\x00\x01"))


def test_rdw_payload_length_mismatch_propagates_from_decode_record() -> None:
    # RDW framing parses fine, but the extracted payload (10 bytes) still
    # doesn't match flat_display's 18-byte layout - decode_record's own
    # exact-match rule (decision 0010) still applies, unchanged.
    root = _root("flat_display")
    with pytest.raises(RecordLengthMismatchError, match="expected 18 bytes, got 10"):
        decode_rdw_record(root, _rdw(bytes(10)))

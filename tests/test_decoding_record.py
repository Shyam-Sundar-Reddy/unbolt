"""decode_record() acceptance tests: real hand-crafted bytes, decoded
against a real fixture's DSL, compared to hand-computed expected values
- the round-trip guarantee (goal.md §7) tested against actual bytes for
the first time, not just ranges.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from unbolt.decoding import decode_packed, decode_record
from unbolt.dsl import build_dsl
from unbolt.dsl.walk import walk_fields
from unbolt.exceptions import RecordLengthMismatchError, UnsupportedDecodeError
from unbolt.parser import parse_copybook

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _root(name: str):
    source = (FIXTURES_DIR / f"{name}.cpy").read_text()
    dsl = build_dsl(parse_copybook(source), source_file=f"{name}.cpy")
    return dsl.roots[0]


def test_flat_display_record_decodes_every_field_exactly() -> None:
    root = _root("flat_display")
    assert root.byte_size == 18

    # CUSTOMER-ID = 123456 (unsigned); CUSTOMER-AGE = -45 (signed);
    # ACCOUNT-BALANCE = 1234567.89 (signed, scale 2).
    data = bytes(
        [0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6]  # CUSTOMER-ID "123456"
        + [0xF0, 0xF4, 0xD5]  # CUSTOMER-AGE "045" negative
        + [0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xC9]  # ACCOUNT-BALANCE +123456789
    )

    values = decode_record(root, data)

    assert values == {
        "CUSTOMER-RECORD.CUSTOMER-ID": Decimal("123456"),
        "CUSTOMER-RECORD.CUSTOMER-AGE": Decimal("-45"),
        "CUSTOMER-RECORD.ACCOUNT-BALANCE": Decimal("1234567.89"),
    }


def test_nested_group_record_decodes_every_leaf_using_its_own_offset() -> None:
    root = _root("nested_groups")
    assert root.byte_size == 25

    data = bytes(
        [0xF0, 0xF0, 0xF0, 0xF0, 0xF0, 0xF0, 0xF4, 0xF2]  # ORDER-ID "00000042"
        + [0xF2, 0xF0, 0xF2, 0xF4]  # ORDER-YEAR "2024"
        + [0xF1, 0xF1]  # ORDER-MONTH "11"
        + [0xF0, 0xF5]  # ORDER-DAY "05"
        + [0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xD9]  # ORDER-TOTAL -1234567.89
    )

    values = decode_record(root, data)

    assert values == {
        "ORDER-RECORD.ORDER-HEADER.ORDER-ID": Decimal("42"),
        "ORDER-RECORD.ORDER-HEADER.ORDER-DATE.ORDER-YEAR": Decimal("2024"),
        "ORDER-RECORD.ORDER-HEADER.ORDER-DATE.ORDER-MONTH": Decimal("11"),
        "ORDER-RECORD.ORDER-HEADER.ORDER-DATE.ORDER-DAY": Decimal("5"),
        "ORDER-RECORD.ORDER-TOTAL": Decimal("-1234567.89"),
    }


def test_wrong_length_record_is_rejected_not_best_effort_decoded() -> None:
    root = _root("flat_display")
    with pytest.raises(RecordLengthMismatchError, match="expected 18 bytes, got 10"):
        decode_record(root, bytes(10))


def test_occurs_field_decode_is_not_supported_yet() -> None:
    root = _root("occurs_table")
    # WAREHOUSE-ID "0001" + ITEM-COUNT "05" decode fine (both plain
    # DISPLAY, no OCCURS) - the rejection must come from ITEM-TABLE.
    data = bytes([0xF0, 0xF0, 0xF0, 0xF1, 0xF0, 0xF5]) + bytes(root.byte_size - 6)
    with pytest.raises(UnsupportedDecodeError, match="OCCURS"):
        decode_record(root, data)


def test_binary_comp_field_decode_is_not_supported_yet() -> None:
    # mixed_usage's RECORD-ID is PIC 9(5) COMP (binary) - still
    # unsupported even though COMP-3 (its next sibling) now is.
    root = _root("mixed_usage")
    with pytest.raises(UnsupportedDecodeError, match="DISPLAY/COMP-3"):
        decode_record(root, bytes(root.byte_size))


def test_comp3_fields_in_a_real_fixture_decode_to_hand_computed_values() -> None:
    # mixed_usage's TRANSACTION-COUNT/UNIT-PRICE are real COMP-3 fields;
    # RECORD-ID (COMP, binary) ahead of them means a full decode_record()
    # can't succeed on this fixture yet (binary decode is a later
    # slice) - so this grounds decode_packed() directly in the real
    # fixture's own digits/scale/byte_size instead.
    dsl = build_dsl(
        parse_copybook((FIXTURES_DIR / "mixed_usage.cpy").read_text()),
        source_file="mixed_usage.cpy",
    )
    by_path = {path: node for node, path in walk_fields(dsl)}
    transaction_count = by_path["FINANCIAL-RECORD.TRANSACTION-COUNT"]
    unit_price = by_path["FINANCIAL-RECORD.UNIT-PRICE"]
    assert (transaction_count.digits, transaction_count.scale, transaction_count.byte_size) == (
        9,
        0,
        5,
    )
    assert (unit_price.digits, unit_price.scale, unit_price.byte_size) == (11, 2, 6)

    # TRANSACTION-COUNT = -123456789
    value = decode_packed(
        bytes([0x12, 0x34, 0x56, 0x78, 0x9D]),
        digits=transaction_count.digits,
        scale=transaction_count.scale,
    )
    assert value == Decimal("-123456789")

    # UNIT-PRICE = 123456789.01
    value = decode_packed(
        bytes([0x12, 0x34, 0x56, 0x78, 0x90, 0x1C]),
        digits=unit_price.digits,
        scale=unit_price.scale,
    )
    assert value == Decimal("123456789.01")


def test_comp3_record_decodes_end_to_end_through_decode_record() -> None:
    source = """
    01  REC.
        05  A PIC S9(9) COMP-3.
        05  B PIC 9(3).
    """
    dsl = build_dsl(parse_copybook(source), source_file="<test>")
    root = dsl.roots[0]
    assert root.byte_size == 5 + 3  # A: 9 digits -> 5 bytes; B: DISPLAY 3 bytes

    data = bytes([0x12, 0x34, 0x56, 0x78, 0x9D]) + bytes([0xF0, 0xF4, 0xF2])  # A=-123456789, B=042

    values = decode_record(root, data)

    assert values == {"REC.A": Decimal("-123456789"), "REC.B": Decimal("42")}


def test_redefines_siblings_each_decode_their_own_view_of_the_shared_bytes() -> None:
    # REDEFINES's offset-sharing (ADR 0008) means two independent fields
    # both read from the same starting offset - that's correct "union of
    # overlaid items" semantics, not a bug: a field and whatever
    # REDEFINES it are two different interpretations of one byte range.
    source = """
    01  REC.
        05  A PIC 9(5).
        05  B REDEFINES A PIC 9(3).
        05  C PIC 9(2).
    """
    dsl = build_dsl(parse_copybook(source), source_file="<test>")
    root = dsl.roots[0]
    assert root.byte_size == 7  # A(5) + C(2); B shares A's bytes, adds none

    data = bytes([0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF9, 0xF8])  # "12345" + "98"

    values = decode_record(root, data)

    assert values["REC.A"] == Decimal("12345")
    assert values["REC.B"] == Decimal("123")  # B's own 3 bytes, same offset as A
    assert values["REC.C"] == Decimal("98")

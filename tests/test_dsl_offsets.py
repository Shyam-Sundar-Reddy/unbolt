"""FieldNode.offset (ADR 0008): the top-down pass build_dsl runs after
byte_size is computed bottom-up. Golden-fixture tests already cover the
common shapes end to end; these exercise specific branches no fixture
does, most importantly a REDEFINES wider than its target pushing the
offset of the sibling that comes after it.
"""

from unbolt.dsl import build_dsl
from unbolt.dsl.walk import walk_fields
from unbolt.parser import parse_copybook


def _offsets(source: str) -> dict[str, int]:
    dsl = build_dsl(parse_copybook(source), source_file="<test>")
    return {path: node.offset for node, path in walk_fields(dsl)}


def test_flat_fields_offset_sequentially() -> None:
    offsets = _offsets(
        """
        01  REC.
            05  A PIC 9(3).
            05  B PIC 9(2).
            05  C PIC 9(4).
        """
    )
    assert offsets == {"REC": 0, "REC.A": 0, "REC.B": 3, "REC.C": 5}


def test_nested_group_offset_is_relative_to_the_record_not_the_group() -> None:
    offsets = _offsets(
        """
        01  REC.
            05  A PIC 9(2).
            05  GRP.
                10  B PIC 9(3).
                10  C PIC 9(1).
        """
    )
    assert offsets == {
        "REC": 0,
        "REC.A": 0,
        "REC.GRP": 2,
        "REC.GRP.B": 2,
        "REC.GRP.C": 5,
    }


def test_occurs_field_offset_is_the_first_occurrence_start() -> None:
    offsets = _offsets(
        """
        01  REC.
            05  A PIC 9(2).
            05  TBL PIC 9(3) OCCURS 4 TIMES.
            05  Z PIC 9(1).
        """
    )
    # TBL's own offset is where occurrence 0 starts; occurrence i starts
    # at that offset + i * byte_size - the decoder's job, not stored
    # per-occurrence here. Z must start after all 4 occurrences (3*4=12).
    assert offsets == {"REC": 0, "REC.A": 0, "REC.TBL": 2, "REC.Z": 14}


def test_redefines_shares_its_targets_offset() -> None:
    offsets = _offsets(
        """
        01  REC.
            05  A PIC X(10).
            05  B REDEFINES A PIC 9(5).
            05  Z PIC 9(1).
        """
    )
    # B is narrower than A (5 < 10) - the footprint doesn't grow, so Z
    # starts right after A's own extent, not after B's.
    assert offsets == {"REC": 0, "REC.A": 0, "REC.B": 0, "REC.Z": 10}


def test_redefines_wider_than_its_target_pushes_the_next_sibling() -> None:
    offsets = _offsets(
        """
        01  REC.
            05  A PIC X(5).
            05  B REDEFINES A PIC X(10).
            05  Z PIC X(3).
        """
    )
    # B (10 bytes) overlays A (5 bytes) starting at the same offset, but
    # is wider - Z must start after B's full extent (10), not A's (5),
    # or Z would overlap bytes 5..9 that B actually occupies.
    assert offsets == {"REC": 0, "REC.A": 0, "REC.B": 0, "REC.Z": 10}


def test_two_successive_redefines_each_wider_keep_pushing_the_cursor() -> None:
    offsets = _offsets(
        """
        01  REC.
            05  A PIC X(5).
            05  B REDEFINES A PIC X(10).
            05  C REDEFINES A PIC X(20).
            05  Z PIC X(1).
        """
    )
    assert offsets == {
        "REC": 0,
        "REC.A": 0,
        "REC.B": 0,
        "REC.C": 0,
        "REC.Z": 20,
    }

from decimal import Decimal

import pytest

from unbolt.datatypes.sizing import describe_datatype, numeric_byte_size
from unbolt.dsl.schema import FieldNode
from unbolt.exceptions import UnsupportedPictureError


def _field(**overrides: object) -> FieldNode:
    defaults: dict[str, object] = dict(
        name="F",
        level=5,
        pic="9(3)",
        usage="DISPLAY",
        signed=False,
        sign_separate=False,
        digits=3,
        scale=0,
        byte_size=3,
        occurs=None,
        redefines=None,
        value=None,
        source_line=1,
        offset=0,
        sign_leading=False,
    )
    defaults.update(overrides)
    return FieldNode(**defaults)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("digits", "expected_bytes"),
    [(1, 2), (4, 2), (5, 4), (9, 4), (10, 8), (18, 8)],
)
def test_binary_tier_boundaries(digits: int, expected_bytes: int) -> None:
    assert numeric_byte_size("COMP", digits, sign_separate=False) == expected_bytes


def test_binary_over_18_digits_is_unsupported() -> None:
    with pytest.raises(UnsupportedPictureError):
        numeric_byte_size("COMP", 19, sign_separate=False)


def test_pic_9_3_rejects_values_above_999() -> None:
    facts = describe_datatype(_field(pic="9(3)", digits=3, scale=0, signed=False, byte_size=3))
    assert facts.min_value == Decimal(0)
    assert facts.max_value == Decimal(999)


def test_pic_s9_9_v99_comp3_matches_goal_md_worked_example() -> None:
    facts = describe_datatype(
        _field(
            pic="S9(9)V99",
            usage="COMP-3",
            signed=True,
            digits=11,
            scale=2,
            byte_size=6,
        )
    )
    assert facts.byte_size == 6
    assert facts.min_value == Decimal("-999999999.99")
    assert facts.max_value == Decimal("999999999.99")


def test_comp_uses_trunc_std_pic_limited_range_not_full_binary() -> None:
    # PIC 9(5) COMP is a 4-byte fullword (up to 4294967295) but TRUNC(STD)
    # caps the *usable* range at what the 5 PIC digits can express.
    facts = describe_datatype(
        _field(pic="9(5)", usage="COMP", signed=False, digits=5, scale=0, byte_size=4)
    )
    assert facts.max_value == Decimal(99999)


def test_comp5_uses_the_full_native_binary_range_not_pic_digits() -> None:
    # Same PIC/digit count as the TRUNC(STD) test above, but COMP-5 always
    # uses the full binary range regardless of TRUNC (decision 0001).
    facts = describe_datatype(
        _field(pic="9(5)", usage="COMP-5", signed=False, digits=5, scale=0, byte_size=4)
    )
    assert facts.max_value == Decimal(2**32 - 1)


def test_group_field_has_no_numeric_range() -> None:
    group = _field(pic=None, digits=0, scale=0, byte_size=10, children=(_field(),))
    with pytest.raises(UnsupportedPictureError):
        describe_datatype(group)


def test_alphanumeric_field_has_no_numeric_range() -> None:
    alpha = _field(pic="X(10)", digits=0, scale=0, signed=False, byte_size=10)
    with pytest.raises(UnsupportedPictureError):
        describe_datatype(alpha)

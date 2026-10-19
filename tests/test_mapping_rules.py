from decimal import Decimal

import pytest

from unbolt.datatypes import TypeFacts
from unbolt.mapping.go_rules import go_decimal_candidates, go_integer_candidates
from unbolt.mapping.java_rules import java_decimal_candidates, java_integer_candidates


def _facts(signed: bool, digits: int, scale: int = 0, byte_size: int = 1) -> TypeFacts:
    max_unscaled = 10**digits - 1
    min_unscaled = -max_unscaled if signed else 0
    scale_factor = Decimal(10) ** scale
    return TypeFacts(
        signed=signed,
        digits=digits,
        scale=scale,
        byte_size=byte_size,
        min_value=Decimal(min_unscaled) / scale_factor,
        max_value=Decimal(max_unscaled) / scale_factor,
    )


def _status(candidates, type_name: str) -> str:
    for c in candidates:
        if c.type_name == type_name:
            return c.status
    raise AssertionError(f"no candidate named {type_name!r}")


def _first_valid(candidates) -> str:
    for c in candidates:
        if c.status == "valid":
            return c.type_name
    raise AssertionError("no valid candidate")


# goal.md §5.7's own boundary table.
@pytest.mark.parametrize(
    ("signed", "digits", "go_first_valid", "java_first_valid"),
    [
        (False, 3, "uint16", "short"),  # PIC 9(3): 0..999
        (True, 4, "int16", "short"),  # PIC S9(4): ±9999
        (True, 9, "int32", "int"),  # PIC S9(9): ±999,999,999
        (True, 18, "int64", "long"),  # PIC S9(18)
        (True, 19, "big.Int", "BigInteger"),  # PIC S9(19+)
    ],
)
def test_integer_boundary_table(signed, digits, go_first_valid, java_first_valid) -> None:
    # Checks the expected type IS valid, not that it's the sole/first
    # winner - a same-width signed type can legitimately also fit an
    # unsigned field's range (e.g. int16 also covers PIC 9(3)'s 0..999);
    # that's a tie, not a bug, so this doesn't assert away ties.
    facts = _facts(signed, digits)
    assert _status(go_integer_candidates(facts), go_first_valid) == "valid"
    assert _status(java_integer_candidates(facts), java_first_valid) == "valid"


def test_go_uint8_rejected_for_pic_9_3() -> None:
    facts = _facts(signed=False, digits=3)
    candidates = go_integer_candidates(facts)
    assert _status(candidates, "uint8") == "invalid"
    assert _status(candidates, "uint16") == "valid"


def test_java_byte_rejected_for_pic_s9_4() -> None:
    facts = _facts(signed=True, digits=4)
    candidates = java_integer_candidates(facts)
    assert _status(candidates, "byte") == "invalid"
    assert _status(candidates, "short") == "valid"


def test_java_has_no_unsigned_so_needs_a_bigger_type_than_go() -> None:
    # PIC 9(19) (unsigned, 19 digits): max is 9,999,999,999,999,999,999.
    # Go's uint64 (max ~1.84e19) covers it; Java's long (max ~9.22e18,
    # Java has no unsigned 64-bit type) doesn't - only BigInteger does.
    facts = _facts(signed=False, digits=19)

    go_candidates = go_integer_candidates(facts)
    assert _status(go_candidates, "int64") == "invalid"
    assert _status(go_candidates, "uint64") == "valid"

    java_candidates = java_integer_candidates(facts)
    assert _status(java_candidates, "long") == "invalid"
    assert _first_valid(java_candidates) == "BigInteger"


def test_go_decimal_fits_scaled_int64() -> None:
    # PIC S9(9)V99 COMP-3: 11 digits, scale 2 - goal.md's own worked example.
    facts = _facts(signed=True, digits=9, scale=2, byte_size=6)
    candidates = go_decimal_candidates(facts)
    assert _status(candidates, "float32") == "invalid"
    assert _status(candidates, "float64") == "invalid"
    assert _status(candidates, "int64 (scaled)") == "valid"


def test_go_decimal_falls_back_to_string_when_int64_overflows() -> None:
    # 20 digits, scale 2: unscaled value needs 20 digits, int64 maxes at 19.
    facts = _facts(signed=True, digits=20, scale=2, byte_size=20)
    candidates = go_decimal_candidates(facts)
    assert _status(candidates, "int64 (scaled)") == "invalid"
    assert _status(candidates, "string") == "valid"


def test_java_decimal_is_always_bigdecimal_never_float() -> None:
    facts = _facts(signed=True, digits=9, scale=2, byte_size=6)
    candidates = java_decimal_candidates(facts)
    assert _status(candidates, "float") == "invalid"
    assert _status(candidates, "double") == "invalid"
    assert _status(candidates, "BigDecimal") == "valid"
    for c in candidates:
        if c.status == "invalid":
            assert "hard rule" in c.rationale

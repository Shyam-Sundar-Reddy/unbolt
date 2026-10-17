import pytest

from unbolt.exceptions import InputTooLargeError, InvalidInputError
from unbolt.parser import parse_copybook


def test_level_66_renames_is_a_diagnostic_not_a_node() -> None:
    result = parse_copybook(
        """
        01  REC.
            05  A PIC 9(1).
        66  R RENAMES A.
        """
    )
    assert [d.code for d in result.diagnostics] == ["CBL-W020"]
    assert [r.name for r in result.roots] == ["REC"]


def test_occurs_depending_on_is_a_diagnostic_and_not_a_table() -> None:
    result = parse_copybook(
        """
        01  REC.
            05  N PIC 9(2).
            05  ROW PIC 9(1) OCCURS 1 TO 10 TIMES DEPENDING ON N.
        """
    )
    assert "CBL-W030" in [d.code for d in result.diagnostics]
    row = result.roots[0].children[1]
    assert row.occurs is None


def test_copy_replacing_is_a_diagnostic_and_entry_is_skipped() -> None:
    result = parse_copybook(
        """
        COPY SOME-MEMBER REPLACING ==X== BY ==Y==.
        01  REC PIC 9(1).
        """
    )
    assert [d.code for d in result.diagnostics] == ["CBL-W010"]
    assert [r.name for r in result.roots] == ["REC"]


def test_unrecognized_clause_token_does_not_crash_the_parse() -> None:
    result = parse_copybook("01 X PIC 9(1) SOME-UNKNOWN-CLAUSE.")
    assert "CBL-W040" in [d.code for d in result.diagnostics]
    assert result.roots[0].name == "X"


def test_malformed_level_number_is_a_diagnostic() -> None:
    result = parse_copybook("NOT-A-LEVEL X PIC 9(1).")
    assert [d.code for d in result.diagnostics] == ["CBL-E001"]
    assert result.roots == ()


def test_empty_source_raises_invalid_input() -> None:
    with pytest.raises(InvalidInputError):
        parse_copybook("   \n  ")


def test_source_over_the_size_limit_raises() -> None:
    huge = "01 X PIC 9(1).\n" * 200_000
    with pytest.raises(InputTooLargeError):
        parse_copybook(huge)


def test_unsupported_dialect_raises() -> None:
    with pytest.raises(InvalidInputError):
        parse_copybook("01 X PIC 9(1).", dialect="gnucobol")

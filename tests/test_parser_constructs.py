from unbolt.dsl import build_dsl
from unbolt.parser import parse_copybook


def _parse(source: str):
    result = parse_copybook(source)
    assert result.diagnostics == ()
    return build_dsl(result, source_file="<test>").roots


def test_level_hierarchy_builds_parent_child_tree() -> None:
    (root,) = _parse(
        """
        01  A.
            05  B PIC 9(1).
            05  C.
                10  D PIC 9(1).
        """
    )
    assert [c.name for c in root.children] == ["B", "C"]
    assert [c.name for c in root.children[1].children] == ["D"]


def test_level_77_is_a_standalone_root_not_nested() -> None:
    roots = _parse(
        """
        01  A.
            05  B PIC 9(1).
        77  STANDALONE PIC 9(1).
        """
    )
    assert [r.name for r in roots] == ["A", "STANDALONE"]
    assert roots[1].children == ()


def test_pic_unsigned_integer() -> None:
    (root,) = _parse("01 X PIC 9(6).")
    assert (root.signed, root.digits, root.scale) == (False, 6, 0)


def test_pic_signed_integer() -> None:
    (root,) = _parse("01 X PIC S9(3).")
    assert (root.signed, root.digits, root.scale) == (True, 3, 0)


def test_pic_signed_decimal_with_implied_point() -> None:
    (root,) = _parse("01 X PIC S9(7)V99.")
    assert (root.signed, root.digits, root.scale) == (True, 9, 2)


def test_usage_defaults_to_display() -> None:
    (root,) = _parse("01 X PIC 9(3).")
    assert root.usage == "DISPLAY"


def test_usage_bare_keyword_without_the_word_usage() -> None:
    (root,) = _parse("01 X PIC S9(9) COMP-3.")
    assert root.usage == "COMP-3"


def test_usage_explicit_with_is() -> None:
    (root,) = _parse("01 X PIC S9(9) USAGE IS COMP-3.")
    assert root.usage == "COMP-3"


def test_usage_computational_synonym_normalizes() -> None:
    (root,) = _parse("01 X PIC S9(9) COMPUTATIONAL-3.")
    assert root.usage == "COMP-3"


def test_occurs_fixed_count() -> None:
    (root,) = _parse(
        """
        01  TABLE.
            05  ROW OCCURS 3 TIMES.
                10  CELL PIC 9(1).
        """
    )
    assert root.children[0].occurs == 3


def test_redefines_is_captured_as_metadata() -> None:
    (root,) = _parse(
        """
        01  REC.
            05  A PIC X(4).
            05  B REDEFINES A PIC 9(4).
        """
    )
    assert root.children[1].redefines == "A"


def test_sign_separate_adds_one_byte_to_display() -> None:
    (root,) = _parse("01 X PIC S9(3) SIGN IS LEADING SEPARATE.")
    assert root.sign_separate is True
    assert root.byte_size == 4  # 3 digits + 1 separate sign byte


def test_comp1_and_comp2_have_no_pic_and_fixed_byte_size() -> None:
    (root,) = _parse(
        """
        01  REC.
            05  F PIC 9(1).
            05  S COMP-1.
            05  D COMP-2.
        """
    )
    single, double = root.children[1], root.children[2]
    assert (single.pic, single.byte_size) == (None, 4)
    assert (double.pic, double.byte_size) == (None, 8)

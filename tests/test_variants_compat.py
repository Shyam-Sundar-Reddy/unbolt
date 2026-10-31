"""classify_compatibility() tests (decision 0011). The group-vs-leaf
signature bug (a group's own byte_size naturally growing when a
trailing child is added was wrongly flagged as a breaking change on
the group itself) was caught by actually running the first case before
trusting it - these tests lock that fix in.
"""

from unbolt.dsl import build_dsl
from unbolt.parser import parse_copybook
from unbolt.variants import classify_compatibility


def _root(source: str):
    return build_dsl(parse_copybook(source), source_file="<test>").roots[0]


def test_identical_copybooks_are_full() -> None:
    source = "01 X.\n  05 A PIC 9(3).\n  05 B PIC 9(2)."
    result = classify_compatibility(_root(source), _root(source))
    assert result.compatibility == "FULL"
    assert result.changes == ()


def test_trailing_field_added_is_forward() -> None:
    old = _root("01 X.\n  05 A PIC 9(3).")
    new = _root("01 X.\n  05 A PIC 9(3).\n  05 B PIC 9(2).")
    result = classify_compatibility(old, new)
    assert result.compatibility == "FORWARD"
    assert [c.kind for c in result.changes] == ["added"]
    assert result.changes[0].field_path == "X.B"


def test_multiple_trailing_fields_added_is_forward() -> None:
    old = _root("01 X.\n  05 A PIC 9(3).")
    new = _root("01 X.\n  05 A PIC 9(3).\n  05 B PIC 9(2).\n  05 C PIC 9(1).")
    result = classify_compatibility(old, new)
    assert result.compatibility == "FORWARD"
    assert {c.field_path for c in result.changes} == {"X.B", "X.C"}


def test_trailing_field_added_inside_a_nested_group_is_forward() -> None:
    old = _root("01 X.\n  05 GRP.\n    10 A PIC 9(3).")
    new = _root("01 X.\n  05 GRP.\n    10 A PIC 9(3).\n    10 B PIC 9(2).")
    result = classify_compatibility(old, new)
    assert result.compatibility == "FORWARD"


def test_trailing_field_removed_is_backward() -> None:
    old = _root("01 X.\n  05 A PIC 9(3).\n  05 B PIC 9(2).")
    new = _root("01 X.\n  05 A PIC 9(3).")
    result = classify_compatibility(old, new)
    assert result.compatibility == "BACKWARD"
    assert [c.kind for c in result.changes] == ["removed"]
    assert result.changes[0].field_path == "X.B"


def test_reordered_fields_are_breaking() -> None:
    old = _root("01 X.\n  05 A PIC 9(3).\n  05 B PIC 9(2).")
    new = _root("01 X.\n  05 B PIC 9(2).\n  05 A PIC 9(3).")
    result = classify_compatibility(old, new)
    assert result.compatibility == "BREAKING"
    assert {c.field_path for c in result.changes} == {"X.A", "X.B"}
    assert all(c.kind == "changed" for c in result.changes)


def test_middle_field_removed_is_breaking() -> None:
    old = _root("01 X.\n  05 A PIC 9(3).\n  05 B PIC 9(2).\n  05 C PIC 9(1).")
    new = _root("01 X.\n  05 A PIC 9(3).\n  05 C PIC 9(1).")
    result = classify_compatibility(old, new)
    assert result.compatibility == "BREAKING"
    kinds = {c.field_path: c.kind for c in result.changes}
    assert kinds["X.B"] == "removed"
    assert kinds["X.C"] == "changed"  # C's offset shifted down


def test_middle_field_inserted_is_breaking() -> None:
    old = _root("01 X.\n  05 A PIC 9(3).\n  05 C PIC 9(1).")
    new = _root("01 X.\n  05 A PIC 9(3).\n  05 B PIC 9(2).\n  05 C PIC 9(1).")
    result = classify_compatibility(old, new)
    assert result.compatibility == "BREAKING"
    kinds = {c.field_path: c.kind for c in result.changes}
    assert kinds["X.B"] == "added"
    assert kinds["X.C"] == "changed"  # C's offset shifted up


def test_widened_pic_on_a_shared_field_is_breaking() -> None:
    old = _root("01 X.\n  05 A PIC 9(3).\n  05 B PIC 9(2).")
    new = _root("01 X.\n  05 A PIC 9(5).\n  05 B PIC 9(2).")
    result = classify_compatibility(old, new)
    assert result.compatibility == "BREAKING"
    kinds = {c.field_path: c.kind for c in result.changes}
    assert kinds["X.A"] == "changed"
    assert kinds["X.B"] == "changed"  # B's offset shifted by A's widening


def test_trailing_add_and_trailing_remove_together_is_breaking() -> None:
    # Not treated as a safe "swap" - a consumer expecting B's bytes
    # would misinterpret C's bytes as if they were still B.
    old = _root("01 X.\n  05 A PIC 9(3).\n  05 B PIC 9(2).")
    new = _root("01 X.\n  05 A PIC 9(3).\n  05 C PIC 9(2).")
    result = classify_compatibility(old, new)
    assert result.compatibility == "BREAKING"
    kinds = {c.field_path: c.kind for c in result.changes}
    assert kinds["X.B"] == "removed"
    assert kinds["X.C"] == "added"


def test_group_occurs_change_is_breaking() -> None:
    old = _root("01 X.\n  05 GRP OCCURS 5 TIMES.\n    10 A PIC 9(3).")
    new = _root("01 X.\n  05 GRP OCCURS 6 TIMES.\n    10 A PIC 9(3).")
    result = classify_compatibility(old, new)
    assert result.compatibility == "BREAKING"
    assert any(c.field_path == "X.GRP" and c.kind == "changed" for c in result.changes)


def test_group_byte_size_growth_from_a_trailing_child_is_not_itself_a_change() -> None:
    # Regression: a group's own byte_size is derived from its children -
    # comparing it directly double-counts a child's own added/removed
    # signal as a second, spurious "the group itself changed" signal,
    # which would wrongly force BREAKING for every trailing addition.
    old = _root("01 X.\n  05 GRP.\n    10 A PIC 9(3).\n  05 Z PIC 9(1).")
    new = _root("01 X.\n  05 GRP.\n    10 A PIC 9(3).\n    10 B PIC 9(2).\n  05 Z PIC 9(1).")
    result = classify_compatibility(old, new)
    assert result.compatibility == "BREAKING"  # Z's offset shifts - genuinely breaking
    kinds = {c.field_path: c.kind for c in result.changes}
    assert kinds["X.GRP.B"] == "added"
    assert kinds["X.Z"] == "changed"
    assert "X.GRP" not in kinds  # the group itself isn't separately flagged

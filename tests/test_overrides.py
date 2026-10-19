import pytest

from unbolt.exceptions import InvalidChoiceError
from unbolt.overrides import Overrides, apply_override


def test_apply_override_accepts_a_valid_choice() -> None:
    result = apply_override(
        Overrides(),
        "REC.AGE",
        "uint16",
        "fits and matches semantics",
        valid_choices=["uint16", "int32"],
    )
    (entry,) = result.entries
    assert (entry.field_path, entry.choice, entry.reason) == (
        "REC.AGE",
        "uint16",
        "fits and matches semantics",
    )


def test_apply_override_rejects_an_invalid_choice() -> None:
    with pytest.raises(InvalidChoiceError):
        apply_override(Overrides(), "REC.AGE", "float64", "no", valid_choices=["uint16", "int32"])


def test_apply_override_force_bypasses_the_check() -> None:
    result = apply_override(
        Overrides(),
        "REC.AGE",
        "float64",
        "I know what I'm doing",
        valid_choices=["uint16"],
        force=True,
    )
    assert result.entries[0].choice == "float64"


def test_apply_override_replaces_the_prior_override_for_the_same_field() -> None:
    first = apply_override(Overrides(), "REC.AGE", "uint16", "first", valid_choices=["uint16"])
    second = apply_override(first, "REC.AGE", "int32", "changed my mind", valid_choices=["int32"])
    assert [e.choice for e in second.entries] == ["int32"]


def test_apply_override_does_not_mutate_the_input() -> None:
    original = Overrides()
    apply_override(original, "REC.AGE", "uint16", "x", valid_choices=["uint16"])
    assert original.entries == ()

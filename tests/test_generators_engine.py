import pytest

from unbolt.dsl import build_dsl
from unbolt.exceptions import UnapprovedMappingError, UnknownTargetError, UnsupportedDecodeError
from unbolt.generators import generate_code
from unbolt.mapping import recommend_mappings
from unbolt.overrides import Overrides, apply_override
from unbolt.parser import parse_copybook


def _dsl(source: str):
    return build_dsl(parse_copybook(source), source_file="<test>")


def test_go_target_returns_gen_go() -> None:
    dsl = _dsl("01 X PIC 9(3).")
    files = generate_code(dsl, recommend_mappings(dsl, "go"), "go")
    assert set(files) == {"gen.go"}
    assert "type X" in files["gen.go"]


def test_java_target_returns_one_file_per_class() -> None:
    dsl = _dsl("01 X PIC 9(3).")
    files = generate_code(dsl, recommend_mappings(dsl, "java"), "java")
    assert set(files) == {"X.java"}


def test_unknown_target_raises() -> None:
    dsl = _dsl("01 X PIC 9(3).")
    with pytest.raises(UnknownTargetError):
        generate_code(dsl, recommend_mappings(dsl, "go"), "rust")


def test_unapproved_field_raises_before_any_file_is_produced() -> None:
    dsl = _dsl("01 REC.\n    05 S COMP-1.")
    with pytest.raises(UnapprovedMappingError):
        generate_code(dsl, recommend_mappings(dsl, "go"), "go")


def test_an_override_resolves_what_would_otherwise_be_unapproved() -> None:
    dsl = _dsl("01 REC.\n    05 S COMP-1.")
    overrides = apply_override(
        Overrides(), "REC.S", "float32", "best-effort", valid_choices=[], force=True
    )
    files = generate_code(dsl, recommend_mappings(dsl, "go"), "go", overrides=overrides)
    assert "S float32" in files["gen.go"]


def test_emit_decoder_returns_gen_decoder_go() -> None:
    dsl = _dsl("01 REC.\n    05 AGE PIC S9(3).")
    files = generate_code(dsl, recommend_mappings(dsl, "go"), "go", emit="decoder")
    assert set(files) == {"gen_decoder.go"}
    assert "func (r *Rec) Age() (int16, error) {" in files["gen_decoder.go"]


def test_emit_decoder_returns_one_java_decoder_file_per_class() -> None:
    dsl = _dsl("01 REC.\n    05 AGE PIC S9(3).")
    files = generate_code(dsl, recommend_mappings(dsl, "java"), "java", emit="decoder")
    assert set(files) == {"Rec.java"}
    assert "public short getAge() {" in files["Rec.java"]


def test_emit_decoder_rejects_unknown_target() -> None:
    dsl = _dsl("01 REC.\n    05 AGE PIC S9(3).")
    with pytest.raises(UnknownTargetError):
        generate_code(dsl, recommend_mappings(dsl, "go"), "rust", emit="decoder")


def test_emit_decoder_propagates_out_of_scope_errors() -> None:
    # Scalar root (no group) is outside the Go decoder's current slice -
    # generate_code must not swallow or reinterpret that error.
    dsl = _dsl("01 X PIC 9(3).")
    with pytest.raises(UnsupportedDecodeError, match="root must be a group"):
        generate_code(dsl, recommend_mappings(dsl, "go"), "go", emit="decoder")

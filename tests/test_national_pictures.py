from unbolt.datatypes.sizing import is_national_pic, national_pic_width
from unbolt.dsl import build_dsl
from unbolt.generators import generate_code
from unbolt.mapping import recommend_mappings
from unbolt.parser import parse_copybook
from unbolt.performance import estimate_storage
from unbolt.validation import validate_conversion


def _dsl(source: str):
    return build_dsl(parse_copybook(source), source_file="<test>")


def test_is_national_pic_detects_n_and_g() -> None:
    assert is_national_pic("N(4)")
    assert is_national_pic("G(10)")


def test_is_national_pic_false_for_plain_numeric_and_alphanumeric() -> None:
    assert not is_national_pic("S9(7)V99")
    assert not is_national_pic("X(10)")
    assert not is_national_pic("9(3)")


def test_national_pic_width_is_two_bytes_per_character() -> None:
    assert national_pic_width("N(4)") == 8
    assert national_pic_width("G(10)") == 20
    assert national_pic_width("NN") == 4


def test_national_picture_raises_a_diagnostic_not_a_silent_miscount() -> None:
    # Regression: before CBL-W060, is_alpha_pic/is_edited_pic both return
    # False for "N(4)" (neither recognizes N/G), so it fell through to
    # the plain numeric path and silently sized as digits=0, byte_size=0.
    result = parse_copybook("01 X PIC N(4).")
    assert [d.code for d in result.diagnostics] == ["CBL-W060"]


def test_national_picture_field_is_sized_as_double_byte_text_not_digits() -> None:
    dsl = _dsl("01 X PIC N(4).")
    (field,) = dsl.roots[0].children if dsl.roots[0].children else (dsl.roots[0],)
    assert field.digits == 0
    assert field.byte_size == 8


def test_national_picture_excluded_from_numeric_mapping() -> None:
    dsl = _dsl("01 REC.\n    05 NAME PIC N(4).\n    05 AGE PIC 9(3).")
    mapping = recommend_mappings(dsl, "go")
    assert {f.field_path for f in mapping.fields} == {"REC.AGE"}


def test_national_picture_generates_as_string_go_and_java() -> None:
    dsl = _dsl("01 REC.\n    05 NAME PIC N(4).\n    05 AGE PIC 9(3).")
    go_mapping = recommend_mappings(dsl, "go")
    go_files = generate_code(dsl, go_mapping, "go")
    assert "Name string" in go_files["gen.go"]

    java_mapping = recommend_mappings(dsl, "java")
    java_files = generate_code(dsl, java_mapping, "java")
    assert "String name" in next(iter(java_files.values()))


def test_national_picture_produces_no_validation_findings() -> None:
    dsl = _dsl("01 REC.\n    05 NAME PIC N(4).\n    05 AGE PIC 9(3).")
    mapping = recommend_mappings(dsl, "go")
    generated = generate_code(dsl, mapping, "go")
    validation = validate_conversion(dsl, mapping, generated)
    assert validation.findings == ()


def test_national_picture_counted_in_storage_estimate_not_silently_dropped() -> None:
    dsl = _dsl("01 REC.\n    05 NAME PIC N(4).\n    05 AGE PIC 9(3).")
    mapping = recommend_mappings(dsl, "go")
    (est,) = estimate_storage(dsl, mapping)
    name = next(f for f in est.fields if f.field_path.endswith("NAME"))
    assert (name.target_type, name.target_bytes) == ("string", 8)
    assert est.target_record_bytes == 8 + 2  # NAME (string) + AGE (int16)

from unbolt.datatypes.sizing import edited_pic_width, is_edited_pic
from unbolt.dsl import build_dsl
from unbolt.generators import generate_code
from unbolt.mapping import recommend_mappings
from unbolt.parser import parse_copybook
from unbolt.performance import estimate_storage
from unbolt.validation import validate_conversion


def _dsl(source: str):
    return build_dsl(parse_copybook(source), source_file="<test>")


def test_is_edited_pic_detects_each_kind_of_symbol() -> None:
    for pic in ("ZZ9", "**9", "$$9", "9,999", "999.99", "+999", "-999", "999CR", "999DB"):
        assert is_edited_pic(pic), pic


def test_is_edited_pic_false_for_plain_numeric_and_alphanumeric() -> None:
    assert not is_edited_pic("S9(7)V99")
    assert not is_edited_pic("X(10)")
    assert not is_edited_pic("9(3)")


def test_edited_pic_width_counts_every_symbol_position() -> None:
    # Z,Z,',',Z,Z,9,'.',9,9 = 9 characters.
    assert edited_pic_width("ZZ,ZZ9.99") == 9
    assert edited_pic_width("999CR") == 5  # 3 nines + 2 for CR
    assert edited_pic_width("9(5)") == 5


def test_edited_picture_raises_a_diagnostic_not_a_silent_miscount() -> None:
    result = parse_copybook("01 X PIC ZZ,ZZ9.99.")
    assert [d.code for d in result.diagnostics] == ["CBL-W050"]


def test_edited_picture_field_is_sized_as_text_not_digits() -> None:
    dsl = _dsl("01 X PIC ZZ,ZZ9.99.")
    (field,) = dsl.roots[0].children if dsl.roots[0].children else (dsl.roots[0],)
    assert field.digits == 0
    assert field.byte_size == 9


def test_edited_picture_excluded_from_numeric_mapping() -> None:
    dsl = _dsl("01 REC.\n    05 PRICE PIC ZZ,ZZ9.99.\n    05 AGE PIC 9(3).")
    mapping = recommend_mappings(dsl, "go")
    assert {f.field_path for f in mapping.fields} == {"REC.AGE"}


def test_edited_picture_generates_as_string_go_and_java() -> None:
    dsl = _dsl("01 REC.\n    05 PRICE PIC ZZ,ZZ9.99.\n    05 AGE PIC 9(3).")
    go_mapping = recommend_mappings(dsl, "go")
    go_files = generate_code(dsl, go_mapping, "go")
    assert "Price string" in go_files["gen.go"]

    java_mapping = recommend_mappings(dsl, "java")
    java_files = generate_code(dsl, java_mapping, "java")
    assert "String price" in next(iter(java_files.values()))


def test_edited_picture_produces_no_validation_findings() -> None:
    dsl = _dsl("01 REC.\n    05 PRICE PIC ZZ,ZZ9.99.\n    05 AGE PIC 9(3).")
    mapping = recommend_mappings(dsl, "go")
    generated = generate_code(dsl, mapping, "go")
    validation = validate_conversion(dsl, mapping, generated)
    assert validation.findings == ()


def test_edited_picture_counted_in_storage_estimate_not_silently_dropped() -> None:
    dsl = _dsl("01 REC.\n    05 PRICE PIC ZZ,ZZ9.99.\n    05 AGE PIC 9(3).")
    mapping = recommend_mappings(dsl, "go")
    (est,) = estimate_storage(dsl, mapping)
    price = next(f for f in est.fields if f.field_path.endswith("PRICE"))
    assert (price.target_type, price.target_bytes) == ("string", 9)
    assert est.target_record_bytes == 9 + 2  # PRICE (string) + AGE (int16)

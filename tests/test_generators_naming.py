from unbolt.generators.naming import go_field_name, java_field_name


def test_go_field_name_is_pascal_case() -> None:
    assert go_field_name("ACCOUNT-AGE") == "AccountAge"


def test_java_field_name_is_camel_case() -> None:
    name, diagnostics = java_field_name("ACCOUNT-AGE", source_line=1)
    assert name == "accountAge"
    assert diagnostics == ()


def test_go_reserved_word_like_names_are_unaffected() -> None:
    # Go keywords are always lowercase; the capitalized convention
    # structurally can't collide with them.
    assert go_field_name("TYPE") == "Type"
    assert go_field_name("RETURN") == "Return"


def test_java_reserved_word_collision_gets_suffixed_and_diagnosed() -> None:
    name, diagnostics = java_field_name("CLASS", source_line=7)
    assert name == "class_"
    assert [d.code for d in diagnostics] == ["CBL-I102"]
    assert diagnostics[0].line == 7


def test_java_reserved_literal_null_also_collides() -> None:
    name, diagnostics = java_field_name("NULL", source_line=1)
    assert name == "null_"
    assert len(diagnostics) == 1


def test_java_non_colliding_name_has_no_diagnostic() -> None:
    name, diagnostics = java_field_name("CUSTOMER-ID", source_line=1)
    assert name == "customerId"
    assert diagnostics == ()

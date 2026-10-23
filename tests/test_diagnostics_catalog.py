from unbolt.parser import diagnostics as diag
from unbolt.parser.diagnostics import DIAGNOSTIC_CATALOG

_SAMPLE_DIAGNOSTICS = (
    diag.malformed_entry(1, "x"),
    diag.copy_replacing_unsupported(1),
    diag.renames_unsupported(1),
    diag.occurs_depending_on_unsupported(1),
    diag.unrecognized_clause(1, "X"),
    diag.synchronized_not_modeled(1),
    diag.justified_not_modeled(1),
    diag.java_reserved_word_renamed(1, "class", "class_"),
    diag.blank_when_zero_not_modeled(1),
    diag.edited_picture_detected(1, "ZZ9"),
)


def test_catalog_has_no_duplicate_codes() -> None:
    codes = [row[0] for row in DIAGNOSTIC_CATALOG]
    assert len(codes) == len(set(codes))


def test_every_factory_functions_code_is_cataloged() -> None:
    cataloged = {row[0] for row in DIAGNOSTIC_CATALOG}
    produced = {d.code for d in _SAMPLE_DIAGNOSTICS}
    assert produced <= cataloged


def test_every_cataloged_severity_matches_what_the_factory_produces() -> None:
    severity_by_code = {d.code: d.severity for d in _SAMPLE_DIAGNOSTICS}
    for code, severity, _meaning, _fix in DIAGNOSTIC_CATALOG:
        if code in severity_by_code:
            assert severity_by_code[code] == severity

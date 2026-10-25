import json
from pathlib import Path

import pytest

from unbolt.cli import build_parser, main
from unbolt.exceptions import InvalidInputError, UnapprovedMappingError
from unbolt.overrides import load_overrides

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
FLAT = str(FIXTURES_DIR / "flat_display.cpy")
MIXED = str(FIXTURES_DIR / "mixed_usage.cpy")


def test_parse_happy_path(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["parse", FLAT]) == 0
    assert "no diagnostics" in capsys.readouterr().out


def test_parse_error_path_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        main(["parse", str(FIXTURES_DIR / "does-not-exist.cpy")])


def test_dsl_happy_path(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["dsl", FLAT]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["roots"][0]["name"] == "CUSTOMER-RECORD"


def test_dsl_error_path_empty_source(tmp_path: Path) -> None:
    empty = tmp_path / "empty.cpy"
    empty.write_text("   ")
    with pytest.raises(InvalidInputError):
        main(["dsl", str(empty)])


def test_recommend_happy_path(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["recommend", FLAT, "--target", "go"]) == 0
    out = capsys.readouterr().out
    assert "CUSTOMER-RECORD.CUSTOMER-ID" in out
    assert "valid" in out


def test_recommend_error_path_bad_target() -> None:
    with pytest.raises(SystemExit):
        main(["recommend", FLAT, "--target", "rust"])


def test_override_happy_path_then_visible_to_generate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    overrides_file = str(tmp_path / "overrides.json")
    exit_code = main(
        [
            "override", MIXED, "FINANCIAL-RECORD.SENSOR-READING", "float32",
            "--target", "go", "--reason", "best-effort", "--force",
            "--overrides-file", overrides_file,
        ]
    )
    assert exit_code == 0
    assert "saved" in capsys.readouterr().out
    overrides = load_overrides(overrides_file)
    assert overrides.entries[0].choice == "float32"


def test_override_error_path_invalid_choice_without_force(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="not a valid candidate"):
        main(
            [
                "override", FLAT, "CUSTOMER-RECORD.CUSTOMER-ID", "float64",
                "--target", "go", "--reason", "no",
                "--overrides-file", str(tmp_path / "overrides.json"),
            ]
        )


def test_override_error_path_rejects_an_invalid_status_candidate_without_force(
    tmp_path: Path,
) -> None:
    # Regression: UNIT-PRICE (PIC S9(9)V99 COMP-3) has a "double" candidate
    # - it's a real candidate in java_decimal_candidates(), just status
    # "invalid" (rejected by the never-float-for-decimal hard rule). The
    # old candidate_names() included it in valid_choices regardless of
    # status, so this override silently succeeded without --force.
    with pytest.raises(Exception, match="not a valid candidate"):
        main(
            [
                "override", MIXED, "FINANCIAL-RECORD.UNIT-PRICE", "double",
                "--target", "java", "--reason", "no",
                "--overrides-file", str(tmp_path / "overrides.json"),
            ]
        )


def test_generate_happy_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_dir = tmp_path / "out"
    assert main(["generate", FLAT, "--target", "go", "-o", str(out_dir)]) == 0
    assert "wrote" in capsys.readouterr().out
    assert (out_dir / "gen.go").exists()


def test_generate_error_path_unapproved_field(tmp_path: Path) -> None:
    with pytest.raises(UnapprovedMappingError):
        main(
            [
                "generate", MIXED, "--target", "go", "-o", str(tmp_path / "out"),
                "--overrides-file", str(tmp_path / "overrides.json"),
            ]
        )


def test_validate_happy_path(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", FLAT, "--target", "go"]) == 0
    assert "no findings" in capsys.readouterr().out


def test_validate_error_path_unapproved_field(tmp_path: Path) -> None:
    with pytest.raises(UnapprovedMappingError):
        main(
            [
                "validate", MIXED, "--target", "go",
                "--overrides-file", str(tmp_path / "overrides.json"),
            ]
        )


def test_report_happy_path_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["report", FLAT, "--target", "go", "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["target"] == "go"


def test_mcp_subcommand_wires_to_cmd_mcp_without_a_file_argument() -> None:
    # Doesn't actually run the server (that would block on stdio) - just
    # confirms `unbolt mcp` parses and dispatches correctly.
    args = build_parser().parse_args(["mcp"])
    assert args.func.__name__ == "cmd_mcp"


def test_report_error_path_unapproved_field(tmp_path: Path) -> None:
    with pytest.raises(UnapprovedMappingError):
        main(
            [
                "report", MIXED, "--target", "go",
                "--overrides-file", str(tmp_path / "overrides.json"),
            ]
        )

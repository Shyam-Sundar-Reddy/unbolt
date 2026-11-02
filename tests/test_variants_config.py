"""load_variant_config/validate_variant_config tests (decision 0012):
JSON shape validation, then cross-checking against real parsed
copybooks. Runtime variant selection isn't implemented yet - this is
config loading and structural validation only.
"""

import json
from pathlib import Path

import pytest

from unbolt.dsl import build_dsl
from unbolt.exceptions import InvalidVariantConfigError
from unbolt.parser import parse_copybook
from unbolt.variants.config import (
    VariantConfig,
    VariantRule,
    load_variant_config,
    validate_variant_config,
)


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "variants.json"
    path.write_text(json.dumps(data))
    return path


def _dsl(source: str):
    return build_dsl(parse_copybook(source), source_file="<test>")


def _valid_config_data() -> dict:
    return {
        "discriminator": "RECORD-TYPE",
        "unknown_variant": "reject",
        "variants": [
            {"name": "PRIME", "value": "01", "copybook": "prime.cpy"},
            {"name": "FRAUD", "value": "02", "copybook": "fraud.cpy"},
        ],
    }


def test_load_happy_path(tmp_path: Path) -> None:
    path = _write(tmp_path, _valid_config_data())
    config = load_variant_config(path)
    assert config == VariantConfig(
        discriminator="RECORD-TYPE",
        unknown_variant="reject",
        rules=(
            VariantRule(name="PRIME", value="01", copybook="prime.cpy"),
            VariantRule(name="FRAUD", value="02", copybook="fraud.cpy"),
        ),
    )


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(InvalidVariantConfigError, match="not found"):
        load_variant_config(tmp_path / "nope.json")


def test_load_invalid_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "variants.json"
    path.write_text("{not valid json")
    with pytest.raises(InvalidVariantConfigError, match="invalid JSON"):
        load_variant_config(path)


@pytest.mark.parametrize("missing_key", ["discriminator", "unknown_variant", "variants"])
def test_load_missing_required_key_raises(tmp_path: Path, missing_key: str) -> None:
    data = _valid_config_data()
    del data[missing_key]
    path = _write(tmp_path, data)
    with pytest.raises(InvalidVariantConfigError, match=f"missing required key {missing_key!r}"):
        load_variant_config(path)


def test_load_empty_discriminator_raises(tmp_path: Path) -> None:
    data = _valid_config_data()
    data["discriminator"] = ""
    path = _write(tmp_path, data)
    with pytest.raises(InvalidVariantConfigError, match="discriminator"):
        load_variant_config(path)


def test_load_invalid_unknown_variant_policy_raises(tmp_path: Path) -> None:
    data = _valid_config_data()
    data["unknown_variant"] = "ignore"
    path = _write(tmp_path, data)
    with pytest.raises(InvalidVariantConfigError, match="unknown_variant"):
        load_variant_config(path)


def test_load_empty_variants_list_raises(tmp_path: Path) -> None:
    data = _valid_config_data()
    data["variants"] = []
    path = _write(tmp_path, data)
    with pytest.raises(InvalidVariantConfigError, match="non-empty list"):
        load_variant_config(path)


def test_load_variant_missing_a_field_raises(tmp_path: Path) -> None:
    data = _valid_config_data()
    del data["variants"][0]["copybook"]
    path = _write(tmp_path, data)
    with pytest.raises(InvalidVariantConfigError, match="copybook"):
        load_variant_config(path)


def test_load_duplicate_variant_names_raises(tmp_path: Path) -> None:
    data = _valid_config_data()
    data["variants"][1]["name"] = "PRIME"
    path = _write(tmp_path, data)
    with pytest.raises(InvalidVariantConfigError, match="duplicate variant name"):
        load_variant_config(path)


def test_load_duplicate_discriminator_values_raises(tmp_path: Path) -> None:
    data = _valid_config_data()
    data["variants"][1]["value"] = "01"
    path = _write(tmp_path, data)
    with pytest.raises(InvalidVariantConfigError, match="duplicate discriminator value"):
        load_variant_config(path)


def test_validate_happy_path_does_not_raise() -> None:
    config = VariantConfig(
        discriminator="T", unknown_variant="reject", rules=(VariantRule("A", "1", "a.cpy"),)
    )
    dsl = _dsl("01 REC.\n  05 T PIC X(2).\n  05 B PIC 9(3).")
    validate_variant_config(config, {"A": dsl})  # must not raise


def test_validate_missing_dsl_entry_raises() -> None:
    config = VariantConfig(
        discriminator="T", unknown_variant="reject", rules=(VariantRule("A", "1", "a.cpy"),)
    )
    with pytest.raises(InvalidVariantConfigError, match="no parsed copybook"):
        validate_variant_config(config, {})


def test_validate_discriminator_not_found_raises() -> None:
    config = VariantConfig(
        discriminator="T", unknown_variant="reject", rules=(VariantRule("A", "1", "a.cpy"),)
    )
    dsl = _dsl("01 REC.\n  05 B PIC 9(3).")
    with pytest.raises(InvalidVariantConfigError, match="not found"):
        validate_variant_config(config, {"A": dsl})


def test_validate_ambiguous_discriminator_raises() -> None:
    config = VariantConfig(
        discriminator="T", unknown_variant="reject", rules=(VariantRule("A", "1", "a.cpy"),)
    )
    dsl = _dsl("01 REC.\n  05 T PIC X(2).\n  05 GRP.\n    10 T PIC 9(3).")
    with pytest.raises(InvalidVariantConfigError, match="ambiguous"):
        validate_variant_config(config, {"A": dsl})

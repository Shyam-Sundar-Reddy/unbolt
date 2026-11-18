"""select_variant() acceptance tests: decode a real discriminator value
from bytes and dispatch to the matching variant's decode_record() -
the piece Phase 9 was blocked on until alphanumeric decode existed.
"""

from decimal import Decimal

import pytest

from unbolt.dsl import build_dsl
from unbolt.exceptions import InvalidVariantConfigError, UnknownVariantError
from unbolt.parser import parse_copybook
from unbolt.variants import VariantConfig, VariantRule, select_variant, validate_variant_config


def _dsl(source: str):
    return build_dsl(parse_copybook(source), source_file="<test>")


def _config(unknown_variant: str = "reject") -> VariantConfig:
    return VariantConfig(
        discriminator="T",
        unknown_variant=unknown_variant,  # type: ignore[arg-type]
        rules=(
            VariantRule("PRIME", "01", "prime.cpy"),
            VariantRule("FRAUD", "02", "fraud.cpy"),
        ),
    )


def _dsls() -> dict:
    return {
        "PRIME": _dsl("01 REC.\n  05 T PIC X(2).\n  05 AMT PIC 9(5)."),
        "FRAUD": _dsl("01 REC.\n  05 T PIC X(2).\n  05 FLAG PIC X(1).\n  05 AMT PIC 9(5)."),
    }


def test_selects_prime_variant_and_decodes_its_own_layout() -> None:
    data = "01".encode("cp037") + "12345".encode("cp037")
    selection = select_variant(_config(), _dsls(), data)

    assert selection.variant_name == "PRIME"
    assert selection.values == {"REC.T": "01", "REC.AMT": Decimal("12345")}
    assert selection.raw == data


def test_selects_fraud_variant_with_its_own_different_layout() -> None:
    data = "02".encode("cp037") + "Y".encode("cp037") + "67890".encode("cp037")
    selection = select_variant(_config(), _dsls(), data)

    assert selection.variant_name == "FRAUD"
    assert selection.values == {
        "REC.T": "02",
        "REC.FLAG": "Y",
        "REC.AMT": Decimal("67890"),
    }


def test_numeric_discriminator_matches_regardless_of_leading_zeros() -> None:
    dsls = {
        "A": _dsl("01 REC.\n  05 T PIC 9(2).\n  05 X PIC 9(1)."),
        "B": _dsl("01 REC.\n  05 T PIC 9(2).\n  05 Y PIC 9(1)."),
    }
    config = VariantConfig(
        discriminator="T",
        unknown_variant="reject",
        rules=(VariantRule("A", "1", "a.cpy"), VariantRule("B", "2", "b.cpy")),
    )
    data = "01".encode("cp037") + "9".encode("cp037")  # discriminator "01" matches rule value "1"

    selection = select_variant(config, dsls, data)

    assert selection.variant_name == "A"


def test_unknown_discriminator_rejects_by_default_policy() -> None:
    data = "99".encode("cp037") + "12345".encode("cp037")
    with pytest.raises(UnknownVariantError, match="'99'"):
        select_variant(_config(), _dsls(), data)


def test_unknown_discriminator_passthrough_preserves_raw_bytes() -> None:
    data = "99".encode("cp037") + "12345".encode("cp037")
    selection = select_variant(_config(unknown_variant="passthrough"), _dsls(), data)

    assert selection.variant_name is None
    assert selection.values is None
    assert selection.raw == data


def test_select_variant_runs_validate_variant_config_first() -> None:
    # A config/dsls combination that's structurally invalid (missing
    # variant) must fail the same way validate_variant_config() would,
    # not proceed and fail some other, more confusing way.
    with pytest.raises(InvalidVariantConfigError, match="no parsed copybook"):
        select_variant(_config(), {"PRIME": _dsls()["PRIME"]}, b"\x00" * 7)


def test_inconsistent_discriminator_across_variants_is_rejected() -> None:
    dsls = {
        "PRIME": _dsl("01 REC.\n  05 T PIC X(2).\n  05 AMT PIC 9(5)."),
        "FRAUD": _dsl("01 REC.\n  05 PAD PIC X(1).\n  05 T PIC X(2).\n  05 AMT PIC 9(5)."),
    }
    with pytest.raises(InvalidVariantConfigError, match="different offset/type"):
        validate_variant_config(_config(), dsls)


def test_discriminator_as_a_group_is_rejected() -> None:
    dsls = {
        "PRIME": _dsl("01 REC.\n  05 T.\n    10 A PIC X(1).\n    10 B PIC X(1)."),
        "FRAUD": _dsl("01 REC.\n  05 T.\n    10 A PIC X(1).\n    10 B PIC X(1)."),
    }
    with pytest.raises(InvalidVariantConfigError, match="not a group"):
        validate_variant_config(_config(), dsls)

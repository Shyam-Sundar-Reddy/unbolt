"""Runtime variant selection: decode a real discriminator value from
bytes and dispatch to the matching variant's decode_record() (decision
0012). Pure logic over already-parsed data - the caller is responsible
for loading the config and parsing each variant's copybook; this
module never touches the filesystem.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from unbolt.decoding.codecs import DEFAULT_CODEPAGE
from unbolt.decoding.record import decode_field, decode_record
from unbolt.dsl.schema import Dsl
from unbolt.dsl.walk import fields_named
from unbolt.exceptions import UnknownVariantError
from unbolt.variants.config import VariantConfig, validate_variant_config


@dataclass(frozen=True, slots=True)
class VariantSelection:
    """variant_name/values are None exactly when no rule matched and
    the config's unknown_variant policy is "passthrough" - raw is
    always the untouched input bytes, matched or not.
    """

    variant_name: str | None
    values: dict[str, object] | None
    raw: bytes


def select_variant(
    config: VariantConfig,
    dsls: dict[str, Dsl],
    data: bytes,
    *,
    codepage: str = DEFAULT_CODEPAGE,
) -> VariantSelection:
    """Decode `data`'s discriminator value and dispatch to the matching
    variant's decode_record().

    Args: config (VariantConfig): the loaded, already-cross-validated config.
        dsls (dict[str, Dsl]): {variant_name: Dsl}, one entry per
            config.rules (same shape validate_variant_config takes).
        data (bytes): the record's raw bytes.
        codepage (str): EBCDIC code page; cp037 by default (decision 0010).
    Returns: VariantSelection: the matched variant's name and decoded
        fields, or (on no match, with unknown_variant="passthrough")
        variant_name=None/values=None with raw preserved.
    Raises:
        InvalidVariantConfigError: the config/dsls combination is
            invalid (validate_variant_config() runs first - dispatch
            never proceeds on an unvalidated config).
        UnknownVariantError: no rule matches and unknown_variant is
            "reject" (the default policy choice for a config that
            doesn't say otherwise is still whatever the config states;
            there is no implicit default here).
        RecordLengthMismatchError, UnsupportedDecodeError: propagated
            from the matched variant's decode_record(), unchanged - a
            correctly-identified variant whose own record still fails
            to decode is a real decode error, not an unknown variant.
    """
    validate_variant_config(config, dsls)

    reference_dsl = dsls[config.rules[0].name]
    discriminator_node = fields_named(reference_dsl, config.discriminator)[0]
    raw_discriminator = data[
        discriminator_node.offset : discriminator_node.offset + discriminator_node.byte_size
    ]
    decoded = decode_field(
        discriminator_node, raw_discriminator, codepage=codepage, strip_trailing_spaces=True
    )

    for rule in config.rules:
        if _matches(decoded, rule.value):
            variant_dsl = dsls[rule.name]
            values = decode_record(variant_dsl.roots[0], data, codepage=codepage)
            return VariantSelection(variant_name=rule.name, values=values, raw=data)

    if config.unknown_variant == "reject":
        raise UnknownVariantError(
            f"discriminator value {decoded!r} matches no configured variant"
        )
    return VariantSelection(variant_name=None, values=None, raw=data)


def _matches(decoded: object, rule_value: str) -> bool:
    if isinstance(decoded, str):
        return decoded == rule_value
    try:
        return decoded == Decimal(rule_value)
    except InvalidOperation:
        return False

"""Variant config: JSON declaring a discriminator field and the named
variants it selects among (decision 0012). Load/validate only in this
slice - runtime variant selection (decode the discriminator, dispatch
to the matching copybook, UnknownVariant fallback with raw bytes
preserved) is a later slice, gated on alphanumeric field decode
existing (most real discriminator fields are PIC X, not numeric, and
unbolt.decoding doesn't decode alphanumeric fields yet).
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from unbolt.dsl.schema import Dsl, FieldNode
from unbolt.dsl.walk import walk_from
from unbolt.exceptions import InvalidVariantConfigError

UnknownVariantPolicy = Literal["reject", "passthrough"]
_ALLOWED_POLICIES: tuple[UnknownVariantPolicy, ...] = ("reject", "passthrough")


@dataclass(frozen=True, slots=True)
class VariantRule:
    name: str
    value: str
    copybook: str


@dataclass(frozen=True, slots=True)
class VariantConfig:
    discriminator: str
    unknown_variant: UnknownVariantPolicy
    rules: tuple[VariantRule, ...]


def load_variant_config(path: str | Path) -> VariantConfig:
    """Load and shape-validate a variant config JSON file.

    Args: path (str | Path): the config file's path.
    Returns: VariantConfig: discriminator, unknown-variant policy, rules.
    Raises:
        InvalidVariantConfigError: the file is missing, isn't valid
            JSON, is missing a required key, a value has the wrong
            type, `unknown_variant` isn't "reject"/"passthrough", or
            two rules share a name or a discriminator value.
    Example:
        >>> import json, tempfile, os
        >>> body = {
        ...     "discriminator": "T", "unknown_variant": "reject",
        ...     "variants": [{"name": "A", "value": "1", "copybook": "a.cpy"}],
        ... }
        >>> fd, path = tempfile.mkstemp(suffix=".json")
        >>> _ = os.write(fd, json.dumps(body).encode())
        >>> os.close(fd)
        >>> load_variant_config(path).discriminator
        'T'
        >>> os.remove(path)
    """
    file_path = Path(path)
    try:
        text = file_path.read_text()
    except FileNotFoundError:
        raise InvalidVariantConfigError(f"{path!r}: file not found") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise InvalidVariantConfigError(f"{path!r}: invalid JSON ({e})") from None

    for key in ("discriminator", "unknown_variant", "variants"):
        if key not in data:
            raise InvalidVariantConfigError(f"{path!r}: missing required key {key!r}")

    discriminator = data["discriminator"]
    if not isinstance(discriminator, str) or not discriminator:
        raise InvalidVariantConfigError(f"{path!r}: 'discriminator' must be a non-empty string")

    unknown_variant = data["unknown_variant"]
    if unknown_variant not in _ALLOWED_POLICIES:
        raise InvalidVariantConfigError(
            f"{path!r}: 'unknown_variant' must be one of {_ALLOWED_POLICIES}, "
            f"got {unknown_variant!r}"
        )

    raw_rules = data["variants"]
    if not isinstance(raw_rules, list) or not raw_rules:
        raise InvalidVariantConfigError(f"{path!r}: 'variants' must be a non-empty list")

    rules = [_parse_rule(path, i, raw) for i, raw in enumerate(raw_rules)]

    names = [r.name for r in rules]
    if len(names) != len(set(names)):
        raise InvalidVariantConfigError(f"{path!r}: duplicate variant name(s) in {names}")
    values = [r.value for r in rules]
    if len(values) != len(set(values)):
        raise InvalidVariantConfigError(f"{path!r}: duplicate discriminator value(s) in {values}")

    return VariantConfig(
        discriminator=discriminator, unknown_variant=unknown_variant, rules=tuple(rules)
    )


def _parse_rule(path: str | Path, index: int, raw: object) -> VariantRule:
    if not isinstance(raw, dict):
        raise InvalidVariantConfigError(f"{path!r}: variants[{index}] must be an object")
    for key in ("name", "value", "copybook"):
        if not isinstance(raw.get(key), str) or not raw[key]:
            raise InvalidVariantConfigError(
                f"{path!r}: variants[{index}] missing or invalid {key!r}"
            )
    return VariantRule(name=raw["name"], value=raw["value"], copybook=raw["copybook"])


def validate_variant_config(config: VariantConfig, dsls: dict[str, Dsl]) -> None:
    """Cross-check a config against already-parsed copybooks.

    Args: config (VariantConfig): the loaded config.
        dsls (dict[str, Dsl]): {variant_name: Dsl}, one entry per
            config.rules - built by the caller (parse_copybook +
            build_dsl on each rule's own copybook file); this function
            never touches the filesystem itself.
    Raises:
        InvalidVariantConfigError: a rule's variant name has no entry
            in `dsls`, or that Dsl has no field named
            `config.discriminator` anywhere in its tree, or more than
            one (an ambiguity this refuses to guess through rather
            than silently picking one).
    """
    for rule in config.rules:
        if rule.name not in dsls:
            raise InvalidVariantConfigError(f"variant {rule.name!r} has no parsed copybook")
        matches = _fields_named(dsls[rule.name], config.discriminator)
        if not matches:
            raise InvalidVariantConfigError(
                f"variant {rule.name!r}: discriminator field {config.discriminator!r} "
                "not found anywhere in its copybook"
            )
        if len(matches) > 1:
            raise InvalidVariantConfigError(
                f"variant {rule.name!r}: discriminator field {config.discriminator!r} "
                f"is ambiguous ({len(matches)} fields share that name)"
            )


def _fields_named(dsl: Dsl, name: str) -> list[FieldNode]:
    return [node for root in dsl.roots for node, _ in walk_from(root) if node.name == name]

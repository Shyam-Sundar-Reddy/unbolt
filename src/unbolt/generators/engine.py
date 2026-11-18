"""generate_code: dsl + mapping + overrides -> {path: content}.

goal.md's signature sketch includes a generic `options` parameter; this
phase doesn't need one - `overrides` is the one real, already-built
concept that affects output, so it's the actual keyword here rather
than an unused placeholder for a shape nothing requires yet.

`emit` (ADR 0009, Phase 10) picks which generator output: "types"
(default - plain structs/POJOs + range validators, decision 0006's
POJO style, unchanged) or "decoder" (flyweight fixed-offset accessors
over a byte buffer - a new, separate artifact, not a replacement).
"""

from typing import Literal

from unbolt.dsl.schema import Dsl
from unbolt.exceptions import UnknownTargetError, UnsupportedDecodeError
from unbolt.generators.go import generate_go
from unbolt.generators.go_decoder import generate_go_decoder
from unbolt.generators.java import generate_java
from unbolt.generators.resolve import resolve_mapping
from unbolt.mapping.model import MappingReport
from unbolt.overrides import Overrides

Emit = Literal["types", "decoder"]


def generate_code(
    dsl: Dsl,
    mapping: MappingReport,
    target: str,
    *,
    overrides: Overrides | None = None,
    emit: Emit = "types",
) -> dict[str, str]:
    """Returns {relative_path: file_content}.

    Args: emit: "types" (plain structs/POJOs, default) or "decoder"
            (flyweight byte-buffer accessors, ADR 0009) - two separate
            generator outputs sharing the same dsl/mapping/overrides
            inputs, never a replacement for one another.
    Raises:
        UnknownTargetError: target isn't "go" or "java".
        UnapprovedMappingError: a field has no override and no valid
            candidate (propagated from resolve_mapping).
        UnsupportedDecodeError: emit="decoder" and either target="java"
            (no Java decoder generator yet) or the DSL/a field is
            outside the Go decoder's current slice (see
            generators.go_decoder's module docstring).
    """
    resolved = resolve_mapping(mapping, overrides if overrides is not None else Overrides())
    if emit == "decoder":
        if target != "go":
            raise UnsupportedDecodeError(
                f"emit='decoder' only supports target='go' so far, got {target!r}"
            )
        return {"gen_decoder.go": generate_go_decoder(dsl, resolved)}
    if target == "go":
        return {"gen.go": generate_go(dsl, resolved)}
    if target == "java":
        return {f"{name}.java": src for name, src in generate_java(dsl, resolved).items()}
    raise UnknownTargetError(f"unknown target {target!r}; expected 'go' or 'java'")

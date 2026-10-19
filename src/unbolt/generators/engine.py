"""generate_code: dsl + mapping + overrides -> {path: content}.

goal.md's signature sketch includes a generic `options` parameter; this
phase doesn't need one - `overrides` is the one real, already-built
concept that affects output, so it's the actual keyword here rather
than an unused placeholder for a shape nothing requires yet.
"""

from unbolt.dsl.schema import Dsl
from unbolt.exceptions import UnknownTargetError
from unbolt.generators.go import generate_go
from unbolt.generators.java import generate_java
from unbolt.generators.resolve import resolve_mapping
from unbolt.mapping.model import MappingReport
from unbolt.overrides import Overrides


def generate_code(
    dsl: Dsl, mapping: MappingReport, target: str, *, overrides: Overrides | None = None
) -> dict[str, str]:
    """Returns {relative_path: file_content}.

    Raises:
        UnknownTargetError: target isn't "go" or "java".
        UnapprovedMappingError: a field has no override and no valid
            candidate (propagated from resolve_mapping).
    """
    resolved = resolve_mapping(mapping, overrides if overrides is not None else Overrides())
    if target == "go":
        return {"gen.go": generate_go(dsl, resolved)}
    if target == "java":
        return {f"{name}.java": src for name, src in generate_java(dsl, resolved).items()}
    raise UnknownTargetError(f"unknown target {target!r}; expected 'go' or 'java'")

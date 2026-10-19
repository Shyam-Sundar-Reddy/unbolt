"""Go struct + range-validator generation.

Struct shape only, decision 0005: a REDEFINES field is generated as an
ordinary separate field with a comment, not a real memory overlay -
there's no decoder yet that would need true aliasing semantics. Type
declarations come out in a bottom-up (children-before-parent) order;
deterministic, just not top-down reading order - Go doesn't care about
declaration order within a file.
"""

from dataclasses import dataclass
from decimal import Decimal

from unbolt.datatypes import describe_datatype
from unbolt.datatypes.sizing import is_alpha_pic
from unbolt.dsl.schema import Dsl, FieldNode
from unbolt.generators.naming import go_field_name

_UNBOUNDED_TYPES = frozenset({"big.Int", "BigInteger", "string"})


@dataclass(frozen=True, slots=True)
class _Validator:
    func_name: str
    param_type: str
    min_value: int
    max_value: int
    field_label: str


def _go_type_name(resolved_type: str) -> str:
    return "int64" if resolved_type == "int64 (scaled)" else resolved_type


def _unscaled_bounds(node: FieldNode) -> tuple[int, int]:
    facts = describe_datatype(node)
    scale_factor = Decimal(10) ** facts.scale
    return int(facts.min_value * scale_factor), int(facts.max_value * scale_factor)


def generate_go(dsl: Dsl, resolved: dict[str, str]) -> str:
    type_decls: list[str] = []
    validators: list[_Validator] = []

    def go_type_for(node: FieldNode, field_path: str) -> str:
        if node.pic is None and node.children:
            name = go_field_name(node.name)
            _emit_struct(node, field_path, name)
            return name
        if node.pic is not None and is_alpha_pic(node.pic):
            return "string"
        resolved_type = resolved[field_path]
        # COMP-1/COMP-2 have no PIC, so there's no digit-derived range to
        # validate against - whatever type an override picked, it's taken
        # as-is, with no range check (goal.md §5.4: no safe default here).
        if node.pic is not None and resolved_type not in _UNBOUNDED_TYPES:
            min_value, max_value = _unscaled_bounds(node)
            validators.append(
                _Validator(
                    func_name=f"Validate{go_field_name(node.name)}",
                    param_type=_go_type_name(resolved_type),
                    min_value=min_value,
                    max_value=max_value,
                    field_label=node.name,
                )
            )
        return _go_type_name(resolved_type)

    def _emit_struct(node: FieldNode, path: str, type_name: str) -> None:
        lines = [f"type {type_name} struct {{"]
        for child in node.children:
            child_path = f"{path}.{child.name}" if path else child.name
            child_type = go_type_for(child, child_path)
            if child.occurs:
                child_type = f"[{child.occurs}]{child_type}"
            comment = f" // REDEFINES {child.redefines}" if child.redefines else ""
            lines.append(f"\t{go_field_name(child.name)} {child_type}{comment}")
        lines.append("}")
        type_decls.append("\n".join(lines))

    for root in dsl.roots:
        root_name = go_field_name(root.name)
        result_type = go_type_for(root, root.name)
        if result_type != root_name:
            # Root is a scalar field, not a group - go_type_for already
            # emitted a struct for a group root under this exact name, but
            # a scalar root needs its own named top-level type alias.
            type_decls.append(f"type {root_name} {result_type}")

    validator_blocks = [_render_validator(v) for v in validators]

    imports = []
    if validators:
        imports.append('"fmt"')
    if any("big.Int" in decl for decl in type_decls):
        imports.append('"math/big"')
    header = "package generated\n"
    if imports:
        header += "\nimport (\n" + "\n".join(f"\t{imp}" for imp in imports) + "\n)\n"

    parts = [header] + type_decls + validator_blocks
    return "\n\n".join(parts) + "\n"


def _render_validator(v: _Validator) -> str:
    return (
        f"func {v.func_name}(v {v.param_type}) error {{\n"
        f'\tif v < {v.min_value} || v > {v.max_value} {{\n'
        f'\t\treturn fmt.Errorf("{v.field_label}: %v outside {v.min_value}..{v.max_value}", v)\n'
        f"\t}}\n"
        f"\treturn nil\n"
        f"}}"
    )

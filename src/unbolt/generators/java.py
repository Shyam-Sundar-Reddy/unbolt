"""Java POJO + range-validator generation (decision 0006: POJO, not
record/Lombok). Mirrors go.py's intent: a nested group becomes a nested
static class (textually nested inside its parent's braces - Java
doesn't allow a floating top-level `static class`, unlike Go's flat
top-level types), OCCURS becomes an array, REDEFINES becomes two
separate fields with a comment (decision 0005 - no byte decoding exists
yet to need real memory aliasing). Getters/setters only - no generated
equals/hashCode/toString; nothing here needs them yet (YAGNI).

Java allows only one public top-level class per file, unlike Go, so
generate_java() returns one compilation unit per DSL root rather than a
single blob - the caller (generate_code) maps each to its own .java path.
"""

from dataclasses import dataclass
from decimal import Decimal

from unbolt.datatypes import describe_datatype
from unbolt.datatypes.sizing import is_alpha_pic, is_edited_pic, is_national_pic
from unbolt.dsl.schema import Dsl, FieldNode
from unbolt.generators.naming import go_field_name, java_field_name

_UNBOUNDED_TYPES = frozenset({"BigInteger", "BigDecimal"})
_IMPORTS = {
    "BigInteger": "java.math.BigInteger",
    "BigDecimal": "java.math.BigDecimal",
}


@dataclass(frozen=True, slots=True)
class _Validator:
    method_name: str
    param_type: str
    min_value: int
    max_value: int
    field_label: str


def _unscaled_bounds(node: FieldNode) -> tuple[int, int]:
    facts = describe_datatype(node)
    scale_factor = Decimal(10) ** facts.scale
    return int(facts.min_value * scale_factor), int(facts.max_value * scale_factor)


def generate_java(dsl: Dsl, resolved: dict[str, str]) -> dict[str, str]:
    """Returns {ClassName: source}, one compilation unit per DSL root."""
    return {
        go_field_name(root.name): _generate_one_root(root, root.name, resolved)
        for root in dsl.roots
    }


def _scalar_type_and_validator(
    node: FieldNode, field_path: str, resolved: dict[str, str], validators: list[_Validator]
) -> str:
    if node.pic is not None and (
        is_alpha_pic(node.pic) or is_edited_pic(node.pic) or is_national_pic(node.pic)
    ):
        return "String"
    type_name = resolved[field_path]
    if node.pic is not None and type_name not in _UNBOUNDED_TYPES:
        min_value, max_value = _unscaled_bounds(node)
        method_name, _ = java_field_name(f"VALIDATE-{node.name}", source_line=node.source_line)
        validators.append(_Validator(method_name, type_name, min_value, max_value, node.name))
    return type_name


def _render_class(
    node: FieldNode,
    path: str,
    type_name: str,
    resolved: dict[str, str],
    validators: list[_Validator],
    imports: set[str],
    *,
    top_level: bool,
) -> str:
    keyword = "public class" if top_level else "public static class"
    field_lines: list[str] = []
    accessor_lines: list[str] = []
    nested_bodies: list[str] = []

    for child in node.children:
        child_path = f"{path}.{child.name}" if path else child.name
        if child.pic is None and child.children:
            child_type = go_field_name(child.name)
            nested_bodies.append(
                _render_class(
                    child, child_path, child_type, resolved, validators, imports, top_level=False
                )
            )
        else:
            child_type = _scalar_type_and_validator(child, child_path, resolved, validators)
            if child_type in _IMPORTS:
                imports.add(_IMPORTS[child_type])
        if child.occurs:
            child_type = f"{child_type}[]"

        field_name, _ = java_field_name(child.name, source_line=child.source_line)
        comment = f"  // REDEFINES {child.redefines}" if child.redefines else ""
        field_lines.append(f"    private {child_type} {field_name};{comment}")
        capitalized = field_name[0].upper() + field_name[1:]
        accessor_lines.append(
            f"    public {child_type} get{capitalized}() {{ return {field_name}; }}"
        )
        accessor_lines.append(
            f"    public void set{capitalized}({child_type} {field_name}) "
            f"{{ this.{field_name} = {field_name}; }}"
        )

    lines = [f"{keyword} {type_name} {{", *field_lines, *accessor_lines]
    for nested in nested_bodies:
        lines.append("")
        lines.extend(("    " + line if line else "") for line in nested.splitlines())
    lines.append("}")
    return "\n".join(lines)


def _generate_one_root(root: FieldNode, root_path: str, resolved: dict[str, str]) -> str:
    validators: list[_Validator] = []
    imports: set[str] = set()
    class_name = go_field_name(root.name)

    if root.pic is None and root.children:
        body = _render_class(
            root, root_path, class_name, resolved, validators, imports, top_level=True
        )
    else:
        value_type = _scalar_type_and_validator(root, root_path, resolved, validators)
        if value_type in _IMPORTS:
            imports.add(_IMPORTS[value_type])
        body = f"public class {class_name} {{\n    public {value_type} value;\n}}"

    # Validator methods must live inside the class too - Java has no
    # floating top-level functions the way a .go file does.
    body = _insert_before_closing_brace(body, [_render_validator(v) for v in validators])

    parts = []
    if imports:
        parts.append("\n".join(f"import {imp};" for imp in sorted(imports)))
    parts.append(body)
    return "\n\n".join(parts) + "\n"


def _insert_before_closing_brace(body: str, blocks: list[str]) -> str:
    if not blocks:
        return body
    lines = body.splitlines()
    closing_brace = lines.pop()
    for block in blocks:
        lines.append("")
        lines.extend(("    " + line if line else "") for line in block.splitlines())
    lines.append(closing_brace)
    return "\n".join(lines)


def _render_validator(v: _Validator) -> str:
    # Java int literals outside [-2^31, 2^31-1] don't compile without an
    # explicit `L` suffix - the compiler doesn't infer it from context.
    suffix = "L" if v.param_type == "long" else ""
    min_literal = f"{v.min_value}{suffix}"
    max_literal = f"{v.max_value}{suffix}"
    return (
        f"public static void {v.method_name}({v.param_type} v) {{\n"
        f"    if (v < {min_literal} || v > {max_literal}) {{\n"
        f'        throw new IllegalArgumentException("{v.field_label}: " + v + '
        f'" outside {v.min_value}..{v.max_value}");\n'
        f"    }}\n"
        f"}}"
    )

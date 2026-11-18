"""Go flyweight decoder generation (ADR 0009): fixed-offset accessor
methods reading directly from a []byte buffer - zero allocation, zero
reflection. A different artifact from generate_go()'s plain structs,
not a replacement for it - decision 0006 stays untouched, and this
output never had a byte buffer to begin with.

Scope, enforced by raising rather than guessing - mirrors
unbolt.decoding's own incremental slicing (Phase 8) applied to code
generation instead of Python-side decode: flat records only (no
nested groups, OCCURS, or REDEFINES), DISPLAY fields only (unsigned,
and signed via trailing overpunch - no SIGN IS SEPARATE/LEADING, no
COMP-3/binary/alphanumeric), and only integer-ladder Go types up to
int64/uint64 (no big.Int/string/float - decision 0004's default
candidate resolution never picks those for a plain integer field
anyway, but a forced override could). Later Phase 10 slices lift
these restrictions one at a time.
"""

from unbolt.datatypes.sizing import is_alpha_pic, is_edited_pic, is_national_pic
from unbolt.dsl.schema import Dsl, FieldNode
from unbolt.exceptions import UnsupportedDecodeError
from unbolt.generators.naming import go_field_name

_INTEGER_GO_TYPES = frozenset(
    {"int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64"}
)


def generate_go_decoder(dsl: Dsl, resolved: dict[str, str]) -> str:
    """Emit a flyweight Go decoder: one struct wrapping a []byte, one
    accessor method per field reading straight from the buffer.

    Args: dsl (Dsl): must have exactly one root, itself a group (not a
            scalar 77-level item) with only flat, non-OCCURS,
            non-REDEFINES, DISPLAY-usage children - this slice's scope.
        resolved (dict[str, str]): field_path -> Go type name, from
            generators.resolve_mapping() (the same input generate_go()
            takes) - the flyweight decoder returns the identical Go
            type the plain struct generator would have chosen.
    Returns: str: a complete .go source file (package generated).
    Raises:
        UnsupportedDecodeError: the DSL or a field is outside this
            slice's scope (see module docstring).
    Example:
        >>> from unbolt.dsl import build_dsl
        >>> from unbolt.mapping import recommend_mappings
        >>> from unbolt.generators import resolve_mapping
        >>> from unbolt.overrides import Overrides
        >>> from unbolt.parser import parse_copybook
        >>> dsl = build_dsl(parse_copybook("01 X.\\n  05 A PIC 9(3)."), source_file="<t>")
        >>> resolved = resolve_mapping(recommend_mappings(dsl, "go"), Overrides())
        >>> "func (r *X) A() (int16, error)" in generate_go_decoder(dsl, resolved)
        True
    """
    if len(dsl.roots) != 1:
        raise UnsupportedDecodeError(
            "go decoder: exactly one DSL root is supported in this slice"
        )
    root = dsl.roots[0]
    if root.pic is not None or not root.children:
        raise UnsupportedDecodeError("go decoder: the root must be a group in this slice")

    struct_name = go_field_name(root.name)
    accessors = [
        _render_accessor(child, f"{root.name}.{child.name}", resolved, struct_name)
        for child in root.children
    ]

    header = [
        "package generated",
        "",
        'import "fmt"',
        "",
        f"type {struct_name} struct {{",
        "\tbuf []byte",
        "}",
        "",
        f"func New{struct_name}(buf []byte) (*{struct_name}, error) {{",
        f"\tif len(buf) != {root.byte_size} {{",
        f'\t\treturn nil, fmt.Errorf("{struct_name}: expected {root.byte_size} bytes, got %d", '
        "len(buf))",
        "\t}",
        f"\treturn &{struct_name}{{buf: buf}}, nil",
        "}",
    ]
    return "\n".join(header) + "\n\n" + "\n\n".join(accessors) + "\n"


def _render_accessor(
    node: FieldNode, field_path: str, resolved: dict[str, str], struct_name: str
) -> str:
    if node.occurs is not None:
        raise UnsupportedDecodeError(f"go decoder: OCCURS field {node.name!r} isn't supported yet")
    if node.redefines is not None:
        raise UnsupportedDecodeError(
            f"go decoder: REDEFINES field {node.name!r} isn't supported yet"
        )
    if node.pic is None or node.children:
        raise UnsupportedDecodeError(
            f"go decoder: group/nested field {node.name!r} isn't supported yet"
        )
    if is_alpha_pic(node.pic) or is_edited_pic(node.pic) or is_national_pic(node.pic):
        raise UnsupportedDecodeError(
            f"go decoder: alphanumeric/edited/national field {node.name!r} isn't supported yet"
        )
    if node.usage.upper() != "DISPLAY":
        raise UnsupportedDecodeError(
            f"go decoder: only DISPLAY fields are supported in this slice, "
            f"got {node.usage!r} for {node.name!r}"
        )
    if node.sign_separate:
        raise UnsupportedDecodeError(
            f"go decoder: SIGN IS SEPARATE field {node.name!r} isn't supported yet"
        )
    if node.sign_leading:
        raise UnsupportedDecodeError(
            f"go decoder: SIGN IS LEADING field {node.name!r} isn't supported yet"
        )

    resolved_type = resolved[field_path]
    # "int64 (scaled)" is decision 0002's marker for a scaled decimal
    # field - the Go type is plain int64; the caller already knows the
    # scale from the DSL/report (same convention generate_go() uses).
    go_type = "int64" if resolved_type == "int64 (scaled)" else resolved_type
    if go_type not in _INTEGER_GO_TYPES:
        raise UnsupportedDecodeError(
            f"go decoder: resolved type {resolved_type!r} for {field_path!r} isn't "
            "supported in this slice (only int8..int64/uint8..uint64, or a scaled int64)"
        )

    method_name = go_field_name(node.name)
    start, end = node.offset, node.offset + node.byte_size
    body = (
        _signed_display_body(method_name, go_type)
        if node.signed
        else _unsigned_display_body(method_name, go_type)
    )
    return (
        f"func (r *{struct_name}) {method_name}() ({go_type}, error) {{\n"
        f"\traw := r.buf[{start}:{end}]\n" + body + "}"
    )


def _unsigned_display_body(method_name: str, go_type: str) -> str:
    return (
        "\tvar v uint64\n"
        "\tfor _, b := range raw {\n"
        "\t\tif b < 0xF0 || b > 0xF9 {\n"
        f'\t\t\treturn 0, fmt.Errorf("{method_name}: byte %#02x is not a DISPLAY digit", b)\n'
        "\t\t}\n"
        "\t\tv = v*10 + uint64(b&0x0F)\n"
        "\t}\n"
        f"\treturn {go_type}(v), nil\n"
    )


def _signed_display_body(method_name: str, go_type: str) -> str:
    return (
        "\tlead := raw[:len(raw)-1]\n"
        "\tlast := raw[len(raw)-1]\n"
        "\tvar v int64\n"
        "\tfor _, b := range lead {\n"
        "\t\tif b < 0xF0 || b > 0xF9 {\n"
        f'\t\t\treturn 0, fmt.Errorf("{method_name}: byte %#02x is not a DISPLAY digit", b)\n'
        "\t\t}\n"
        "\t\tv = v*10 + int64(b&0x0F)\n"
        "\t}\n"
        "\tzone := last & 0xF0\n"
        "\tdigit := last & 0x0F\n"
        "\tif digit > 9 {\n"
        f'\t\treturn 0, fmt.Errorf("{method_name}: last byte %#02x has a non-digit value '
        'nibble %d", last, digit)\n'
        "\t}\n"
        "\tv = v*10 + int64(digit)\n"
        "\tswitch zone {\n"
        "\tcase 0xC0, 0xF0:\n"
        "\t\t// positive\n"
        "\tcase 0xD0:\n"
        "\t\tv = -v\n"
        "\tdefault:\n"
        f'\t\treturn 0, fmt.Errorf("{method_name}: last byte %#02x has an unrecognized sign '
        'nibble %#02x", last, zone)\n'
        "\t}\n"
        f"\treturn {go_type}(v), nil\n"
    )

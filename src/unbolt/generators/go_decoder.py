"""Go flyweight decoder generation (ADR 0009): fixed-offset accessor
methods reading directly from a []byte buffer - zero allocation, zero
reflection. A different artifact from generate_go()'s plain structs,
not a replacement for it - decision 0006 stays untouched, and this
output never had a byte buffer to begin with.

Nested groups get their own struct type, mirroring generate_go()'s own
nested-struct shape for consistency. Since FieldNode.offset is
absolute from the record root (ADR 0008), not relative to its
immediate parent, a nested group's accessor methods read from the
exact same buffer at their own absolute offsets - no separate base-
offset tracking needed; the group's accessor on its parent just hands
over the same buf reference (a slice header copy, not an allocation).

A SIGN IS SEPARATE sign byte is a plain '+'/'-' character (cp037:
0x4E/0x60), checked as a literal byte value directly - no charset
table needed for just two values, the same reasoning that keeps
alphanumeric field decode (which would need the full table) out of
this slice.

Scope, enforced by raising rather than guessing - mirrors
unbolt.decoding's own incremental slicing (Phase 8) applied to code
generation instead of Python-side decode: OCCURS and REDEFINES fields;
DISPLAY (unsigned, and signed via trailing/leading overpunch or
trailing/leading SIGN IS SEPARATE), COMP-3/PACKED-DECIMAL, and
COMP/COMP-4/COMP-5/BINARY leaf fields; and only integer-ladder Go
types up to int64/uint64 (no big.Int/string/float - decision 0004's
default candidate resolution never picks those for a plain integer
field anyway, but a forced override could). Later Phase 10 slices lift the
remaining restrictions one at a time.
"""

from unbolt.datatypes.sizing import (
    is_alpha_pic,
    is_binary_usage,
    is_edited_pic,
    is_national_pic,
    is_packed_usage,
)
from unbolt.dsl.schema import Dsl, FieldNode
from unbolt.exceptions import UnsupportedDecodeError
from unbolt.generators.naming import go_field_name

_INTEGER_GO_TYPES = frozenset(
    {"int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64"}
)
_BINARY_UINT_READER = {2: "Uint16", 4: "Uint32", 8: "Uint64"}
_BINARY_SIGNED_CAST = {2: "int16", 4: "int32", 8: "int64"}

_PACKED_DECIMAL_HELPER = """func decodePackedDecimal(raw []byte, digits int) (int64, error) {
\ttotalNibbles := len(raw) * 2
\tpad := totalNibbles - 1 - digits
\tvar v int64
\tnibbleIndex := 0
\tfor _, b := range raw {
\t\tfor _, n := range [2]byte{b >> 4, b & 0x0F} {
\t\t\tswitch {
\t\t\tcase nibbleIndex == totalNibbles-1:
\t\t\t\tswitch n {
\t\t\t\tcase 0xC, 0xF:
\t\t\t\tcase 0xD:
\t\t\t\t\tv = -v
\t\t\t\tdefault:
\t\t\t\t\treturn 0, fmt.Errorf("packed decimal: unrecognized sign nibble %#x", n)
\t\t\t\t}
\t\t\tcase nibbleIndex < pad:
\t\t\t\tif n != 0 {
\t\t\t\t\treturn 0, fmt.Errorf("packed decimal: non-zero leading pad nibble %#x", n)
\t\t\t\t}
\t\t\tdefault:
\t\t\t\tif n > 9 {
\t\t\t\t\treturn 0, fmt.Errorf("packed decimal: non-digit nibble %#x", n)
\t\t\t\t}
\t\t\t\tv = v*10 + int64(n)
\t\t\t}
\t\t\tnibbleIndex++
\t\t}
\t}
\treturn v, nil
}"""


def generate_go_decoder(dsl: Dsl, resolved: dict[str, str]) -> str:
    """Emit a flyweight Go decoder: one struct per group (root and
    nested), one accessor method per field reading straight from the
    buffer.

    Args: dsl (Dsl): must have exactly one root, itself a group (not a
            scalar 77-level item); every field under it must use a
            supported usage and not be OCCURS/REDEFINES - this slice's
            scope (see module docstring).
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

    needs: set[str] = set()
    struct_decls: list[str] = []
    accessor_blocks: list[str] = []
    struct_name = _render_group(root, root.name, resolved, needs, struct_decls, accessor_blocks)
    accessor_blocks.insert(0, _root_constructor(struct_name, root.byte_size))

    imports = ['"fmt"']
    if "binary" in needs:
        imports.insert(0, '"encoding/binary"')
    header = [
        "package generated",
        "",
        "import (\n" + "\n".join(f"\t{imp}" for imp in imports) + "\n)",
    ]
    blocks = struct_decls + accessor_blocks
    if "packed" in needs:
        blocks.append(_PACKED_DECIMAL_HELPER)
    return "\n".join(header) + "\n\n" + "\n\n".join(blocks) + "\n"


def _root_constructor(struct_name: str, byte_size: int) -> str:
    return (
        f"func New{struct_name}(buf []byte) (*{struct_name}, error) {{\n"
        f"\tif len(buf) != {byte_size} {{\n"
        f'\t\treturn nil, fmt.Errorf("{struct_name}: expected {byte_size} bytes, got %d", '
        "len(buf))\n"
        "\t}\n"
        f"\treturn &{struct_name}{{buf: buf}}, nil\n"
        "}"
    )


def _render_group(
    node: FieldNode,
    field_path: str,
    resolved: dict[str, str],
    needs: set[str],
    struct_decls: list[str],
    accessor_blocks: list[str],
) -> str:
    """Emits this group's struct type, then recurses into its children
    (each appending its own accessor - and, for a nested group, its own
    struct type first). Returns the Go struct type name, so the caller
    (the parent group, or generate_go_decoder for the root) can use it.
    """
    struct_name = go_field_name(node.name)
    struct_decls.append(f"type {struct_name} struct {{\n\tbuf []byte\n}}")
    for child in node.children:
        _render_child(
            child, f"{field_path}.{child.name}", resolved, struct_name, needs,
            struct_decls, accessor_blocks,
        )
    return struct_name


def _render_child(
    node: FieldNode,
    field_path: str,
    resolved: dict[str, str],
    parent_struct_name: str,
    needs: set[str],
    struct_decls: list[str],
    accessor_blocks: list[str],
) -> None:
    if node.occurs is not None:
        raise UnsupportedDecodeError(f"go decoder: OCCURS field {node.name!r} isn't supported yet")
    if node.redefines is not None:
        raise UnsupportedDecodeError(
            f"go decoder: REDEFINES field {node.name!r} isn't supported yet"
        )

    method_name = go_field_name(node.name)

    if node.pic is None and node.children:
        child_struct_name = _render_group(
            node, field_path, resolved, needs, struct_decls, accessor_blocks
        )
        accessor_blocks.append(
            f"func (r *{parent_struct_name}) {method_name}() {child_struct_name} {{\n"
            f"\treturn {child_struct_name}{{buf: r.buf}}\n"
            "}"
        )
        return

    accessor_blocks.append(
        _render_leaf_accessor(node, field_path, resolved, parent_struct_name, needs)
    )


def _render_leaf_accessor(
    node: FieldNode,
    field_path: str,
    resolved: dict[str, str],
    struct_name: str,
    needs: set[str],
) -> str:
    if node.pic is None:
        raise UnsupportedDecodeError(
            f"go decoder: COMP-1/COMP-2 field {node.name!r} isn't supported yet"
        )
    if is_alpha_pic(node.pic) or is_edited_pic(node.pic) or is_national_pic(node.pic):
        raise UnsupportedDecodeError(
            f"go decoder: alphanumeric/edited/national field {node.name!r} isn't supported yet"
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

    if is_packed_usage(node.usage):
        needs.add("packed")
        body = _packed_body(method_name, go_type, node.digits)
    elif is_binary_usage(node.usage):
        needs.add("binary")
        body = _binary_body(node.byte_size, node.signed, go_type)
    elif node.usage.upper() == "DISPLAY":
        if not node.signed:
            body = _unsigned_display_body(method_name, go_type)
        elif node.sign_separate:
            body = _separate_sign_display_body(method_name, go_type, node.sign_leading)
        elif node.sign_leading:
            body = _leading_overpunch_display_body(method_name, go_type)
        else:
            body = _signed_display_body(method_name, go_type)
    else:
        raise UnsupportedDecodeError(
            f"go decoder: only DISPLAY/COMP-3/binary fields are supported in this "
            f"slice, got {node.usage!r} for {node.name!r}"
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


def _leading_overpunch_display_body(method_name: str, go_type: str) -> str:
    return (
        "\tfirst := raw[0]\n"
        "\trest := raw[1:]\n"
        "\tzone := first & 0xF0\n"
        "\tdigit := first & 0x0F\n"
        "\tif digit > 9 {\n"
        f'\t\treturn 0, fmt.Errorf("{method_name}: first byte %#02x has a non-digit value '
        'nibble %d", first, digit)\n'
        "\t}\n"
        "\tvar v int64 = int64(digit)\n"
        "\tfor _, b := range rest {\n"
        "\t\tif b < 0xF0 || b > 0xF9 {\n"
        f'\t\t\treturn 0, fmt.Errorf("{method_name}: byte %#02x is not a DISPLAY digit", b)\n'
        "\t\t}\n"
        "\t\tv = v*10 + int64(b&0x0F)\n"
        "\t}\n"
        "\tswitch zone {\n"
        "\tcase 0xC0, 0xF0:\n"
        "\t\t// positive\n"
        "\tcase 0xD0:\n"
        "\t\tv = -v\n"
        "\tdefault:\n"
        f'\t\treturn 0, fmt.Errorf("{method_name}: first byte %#02x has an unrecognized sign '
        'nibble %#02x", first, zone)\n'
        "\t}\n"
        f"\treturn {go_type}(v), nil\n"
    )


def _separate_sign_display_body(method_name: str, go_type: str, sign_leading: bool) -> str:
    split = (
        "sign, digits := raw[0], raw[1:]"
        if sign_leading
        else "digits, sign := raw[:len(raw)-1], raw[len(raw)-1]"
    )
    return (
        f"\t{split}\n"
        "\tvar v uint64\n"
        "\tfor _, b := range digits {\n"
        "\t\tif b < 0xF0 || b > 0xF9 {\n"
        f'\t\t\treturn 0, fmt.Errorf("{method_name}: byte %#02x is not a DISPLAY digit", b)\n'
        "\t\t}\n"
        "\t\tv = v*10 + uint64(b&0x0F)\n"
        "\t}\n"
        "\tswitch sign {\n"
        "\tcase 0x4E: // '+' (cp037)\n"
        f"\t\treturn {go_type}(v), nil\n"
        "\tcase 0x60: // '-' (cp037)\n"
        f"\t\treturn {go_type}(-int64(v)), nil\n"
        "\tdefault:\n"
        f'\t\treturn 0, fmt.Errorf("{method_name}: separate sign byte %#02x is not \'+\' or '
        '\'-\'", sign)\n'
        "\t}\n"
    )


def _packed_body(method_name: str, go_type: str, digits: int) -> str:
    return (
        f"\tv, err := decodePackedDecimal(raw, {digits})\n"
        "\tif err != nil {\n"
        f'\t\treturn 0, fmt.Errorf("{method_name}: %w", err)\n'
        "\t}\n"
        f"\treturn {go_type}(v), nil\n"
    )


def _binary_body(byte_size: int, signed: bool, go_type: str) -> str:
    reader = _BINARY_UINT_READER[byte_size]
    unsigned_expr = f"binary.BigEndian.{reader}(raw)"
    if not signed:
        return f"\treturn {go_type}({unsigned_expr}), nil\n"
    signed_cast = _BINARY_SIGNED_CAST[byte_size]
    # Sign-extend via a same-width signed cast first (reinterprets the
    # two's-complement bit pattern, matching Python's int.from_bytes(
    # signed=True)), then narrow to the resolved type - skip the outer
    # cast entirely when it would just repeat the same type.
    signed_expr = f"{signed_cast}({unsigned_expr})"
    if go_type == signed_cast:
        return f"\treturn {signed_expr}, nil\n"
    return f"\treturn {go_type}({signed_expr}), nil\n"

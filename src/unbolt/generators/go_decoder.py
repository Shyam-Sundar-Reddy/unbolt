"""Go flyweight decoder generation (ADR 0009): fixed-offset accessor
methods reading directly from a []byte buffer - zero allocation, zero
reflection. A different artifact from generate_go()'s plain structs,
not a replacement for it - decision 0006 stays untouched, and this
output never had a byte buffer to begin with.

Nested groups get their own struct type, mirroring generate_go()'s own
nested-struct shape for consistency. Since FieldNode.offset is
absolute from the record root (ADR 0008), not relative to its
immediate parent, a plain (non-OCCURS) nested group's accessor methods
read from the exact same buffer at their own absolute offsets - no
separate base-offset tracking needed; the group's accessor on its
parent just hands over the same buf reference (a slice header copy,
not an allocation).

OCCURS breaks that "always absolute" assumption: FieldNode.offset/
byte_size for an OCCURS field describe only its first occurrence - any
later occurrence i's bytes are [offset + i*byte_size, offset +
(i+1)*byte_size). So every accessor is generated with a `base`
parameter (a codegen-time int, not a runtime field) meaning "what
absolute offset does this struct's own buf[0] correspond to" - 0
everywhere a struct is reachable without ever passing through an
OCCURS group (identical output to before OCCURS existed), and reset to
the OCCURS group's own node.offset for everything under it, however
deep. An OCCURS leaf gets an `index int` parameter, a bounds check, and
`start := (offset-base) + index*byte_size`; an OCCURS group gets the
same bounds check and reslices `r.buf[start:start+byte_size]` into a
fresh struct value - zero allocation, just a slice header - and that
reslice is exactly what lets the group's own children keep using
absolute-looking literal offsets relative to *that* occurrence's start,
with no index baked into them (every occurrence has the same internal
layout, and the reslice already picked which one). This composes for
OCCURS nested inside OCCURS: each level's reslice resets the
coordinate frame again, independent of any outer level. Indexing is
0-based, matching generate_go()'s own existing `[N]Type` array
representation for OCCURS, not COBOL's 1-based subscripts.

A SIGN IS SEPARATE sign byte is a plain '+'/'-' character (cp037:
0x4E/0x60), checked as a literal byte value directly - no charset
table needed for just two values.

Plain alphanumeric (PIC X/A) fields decode via a hardcoded 256-entry
cp037-to-Unicode lookup table, embedded as a shared Go helper (same
pattern as decodePackedDecimal) - generated from Python's own cp037
codec (never guessed), not Go's golang.org/x/text, so generated Go
code stays a zero-dependency consumer the way every other usage type
here already is. Only cp037 is covered, same as decision 0001/0010
assume everywhere else in this project. The accessor returns a plain
string with no error return - every byte in a full 256-entry table
decodes to something, so there's nothing to fail on, unlike the
digit-validating DISPLAY/packed bodies. It returns the exact
fixed-width text, space-padded, matching decode_alpha()'s own default
(no silent trailing-space stripping) - trimming is left to the caller.

A resolved big.Int field (never decision 0004's default for a plain
integer - the ladder tops out at int64/uint64 - but reachable via a
forced override, or genuinely needed past 18-19 digits) reuses the
same per-usage dispatch as the fixed-width types, just with big.Int
arithmetic and its own shared helpers (decodeDisplayDigitsBig,
decodePackedDecimalBig) - COMP/COMP-4/COMP-5/BINARY never needs it,
since datatypes/sizing.py's binary tier already caps at 8 bytes/
uint64 range.

Scope, enforced by raising rather than guessing - mirrors
unbolt.decoding's own incremental slicing (Phase 8) applied to code
generation instead of Python-side decode: REDEFINES fields (on a group
or a leaf, OCCURS or not - OCCURS and REDEFINES combined still raises,
checked before OCCURS is ever considered); DISPLAY (unsigned, and
signed via trailing/leading overpunch or trailing/leading SIGN IS
SEPARATE), COMP-3/PACKED-DECIMAL, COMP/COMP-4/COMP-5/BINARY, and plain
alphanumeric (PIC X/A) leaf fields, OCCURS or not; edited pictures and
national/DBCS fields; and a forced float override (decision 0004's
default candidate resolution never picks those for a plain integer
field anyway, but a forced override could). Later Phase 10 slices lift
the remaining restrictions one at a time.
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
_BIG_INT_GO_TYPE = "big.Int"
_BINARY_UINT_READER = {2: "Uint16", 4: "Uint32", 8: "Uint64"}
_BINARY_SIGNED_CAST = {2: "int16", 4: "int32", 8: "int64"}

_DISPLAY_DIGITS_BIG_HELPER = """func decodeDisplayDigitsBig(digits []byte) (*big.Int, error) {
\tv := new(big.Int)
\tten := big.NewInt(10)
\tfor _, b := range digits {
\t\tif b < 0xF0 || b > 0xF9 {
\t\t\treturn nil, fmt.Errorf("byte %#02x is not a DISPLAY digit", b)
\t\t}
\t\tv.Mul(v, ten)
\t\tv.Add(v, big.NewInt(int64(b&0x0F)))
\t}
\treturn v, nil
}"""

_PACKED_DECIMAL_BIG_HELPER = """func decodePackedDecimalBig(
\traw []byte, digits int,
) (*big.Int, error) {
\ttotalNibbles := len(raw) * 2
\tpad := totalNibbles - 1 - digits
\tv := new(big.Int)
\tten := big.NewInt(10)
\tnegative := false
\tnibbleIndex := 0
\tfor _, b := range raw {
\t\tfor _, n := range [2]byte{b >> 4, b & 0x0F} {
\t\t\tswitch {
\t\t\tcase nibbleIndex == totalNibbles-1:
\t\t\t\tswitch n {
\t\t\t\tcase 0xC, 0xF:
\t\t\t\tcase 0xD:
\t\t\t\t\tnegative = true
\t\t\t\tdefault:
\t\t\t\t\treturn nil, fmt.Errorf("packed decimal: unrecognized sign nibble %#x", n)
\t\t\t\t}
\t\t\tcase nibbleIndex < pad:
\t\t\t\tif n != 0 {
\t\t\t\t\treturn nil, fmt.Errorf("packed decimal: non-zero leading pad nibble %#x", n)
\t\t\t\t}
\t\t\tdefault:
\t\t\t\tif n > 9 {
\t\t\t\t\treturn nil, fmt.Errorf("packed decimal: non-digit nibble %#x", n)
\t\t\t\t}
\t\t\t\tv.Mul(v, ten)
\t\t\t\tv.Add(v, big.NewInt(int64(n)))
\t\t\t}
\t\t\tnibbleIndex++
\t\t}
\t}
\tif negative {
\t\tv.Neg(v)
\t}
\treturn v, nil
}"""

_CP037_TO_UNICODE_HELPER = """var cp037ToUnicode = [256]rune{
\t0x0000, 0x0001, 0x0002, 0x0003, 0x009C, 0x0009, 0x0086, 0x007F,
\t0x0097, 0x008D, 0x008E, 0x000B, 0x000C, 0x000D, 0x000E, 0x000F,
\t0x0010, 0x0011, 0x0012, 0x0013, 0x009D, 0x0085, 0x0008, 0x0087,
\t0x0018, 0x0019, 0x0092, 0x008F, 0x001C, 0x001D, 0x001E, 0x001F,
\t0x0080, 0x0081, 0x0082, 0x0083, 0x0084, 0x000A, 0x0017, 0x001B,
\t0x0088, 0x0089, 0x008A, 0x008B, 0x008C, 0x0005, 0x0006, 0x0007,
\t0x0090, 0x0091, 0x0016, 0x0093, 0x0094, 0x0095, 0x0096, 0x0004,
\t0x0098, 0x0099, 0x009A, 0x009B, 0x0014, 0x0015, 0x009E, 0x001A,
\t0x0020, 0x00A0, 0x00E2, 0x00E4, 0x00E0, 0x00E1, 0x00E3, 0x00E5,
\t0x00E7, 0x00F1, 0x00A2, 0x002E, 0x003C, 0x0028, 0x002B, 0x007C,
\t0x0026, 0x00E9, 0x00EA, 0x00EB, 0x00E8, 0x00ED, 0x00EE, 0x00EF,
\t0x00EC, 0x00DF, 0x0021, 0x0024, 0x002A, 0x0029, 0x003B, 0x00AC,
\t0x002D, 0x002F, 0x00C2, 0x00C4, 0x00C0, 0x00C1, 0x00C3, 0x00C5,
\t0x00C7, 0x00D1, 0x00A6, 0x002C, 0x0025, 0x005F, 0x003E, 0x003F,
\t0x00F8, 0x00C9, 0x00CA, 0x00CB, 0x00C8, 0x00CD, 0x00CE, 0x00CF,
\t0x00CC, 0x0060, 0x003A, 0x0023, 0x0040, 0x0027, 0x003D, 0x0022,
\t0x00D8, 0x0061, 0x0062, 0x0063, 0x0064, 0x0065, 0x0066, 0x0067,
\t0x0068, 0x0069, 0x00AB, 0x00BB, 0x00F0, 0x00FD, 0x00FE, 0x00B1,
\t0x00B0, 0x006A, 0x006B, 0x006C, 0x006D, 0x006E, 0x006F, 0x0070,
\t0x0071, 0x0072, 0x00AA, 0x00BA, 0x00E6, 0x00B8, 0x00C6, 0x00A4,
\t0x00B5, 0x007E, 0x0073, 0x0074, 0x0075, 0x0076, 0x0077, 0x0078,
\t0x0079, 0x007A, 0x00A1, 0x00BF, 0x00D0, 0x00DD, 0x00DE, 0x00AE,
\t0x005E, 0x00A3, 0x00A5, 0x00B7, 0x00A9, 0x00A7, 0x00B6, 0x00BC,
\t0x00BD, 0x00BE, 0x005B, 0x005D, 0x00AF, 0x00A8, 0x00B4, 0x00D7,
\t0x007B, 0x0041, 0x0042, 0x0043, 0x0044, 0x0045, 0x0046, 0x0047,
\t0x0048, 0x0049, 0x00AD, 0x00F4, 0x00F6, 0x00F2, 0x00F3, 0x00F5,
\t0x007D, 0x004A, 0x004B, 0x004C, 0x004D, 0x004E, 0x004F, 0x0050,
\t0x0051, 0x0052, 0x00B9, 0x00FB, 0x00FC, 0x00F9, 0x00FA, 0x00FF,
\t0x005C, 0x00F7, 0x0053, 0x0054, 0x0055, 0x0056, 0x0057, 0x0058,
\t0x0059, 0x005A, 0x00B2, 0x00D4, 0x00D6, 0x00D2, 0x00D3, 0x00D5,
\t0x0030, 0x0031, 0x0032, 0x0033, 0x0034, 0x0035, 0x0036, 0x0037,
\t0x0038, 0x0039, 0x00B3, 0x00DB, 0x00DC, 0x00D9, 0x00DA, 0x009F,
}

func decodeAlphaCP037(raw []byte) string {
\trunes := make([]rune, len(raw))
\tfor i, b := range raw {
\t\trunes[i] = cp037ToUnicode[b]
\t}
\treturn string(runes)
}"""

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
    struct_name = _render_group(
        root, root.name, resolved, needs, struct_decls, accessor_blocks, root.offset
    )
    accessor_blocks.insert(0, _root_constructor(struct_name, root.byte_size))

    imports = {'"fmt"'}
    if "binary" in needs:
        imports.add('"encoding/binary"')
    if "bigint" in needs:
        imports.add('"math/big"')
    header = [
        "package generated",
        "",
        "import (\n" + "\n".join(f"\t{imp}" for imp in sorted(imports)) + "\n)",
    ]
    blocks = struct_decls + accessor_blocks
    if "packed" in needs:
        blocks.append(_PACKED_DECIMAL_HELPER)
    if "alpha" in needs:
        blocks.append(_CP037_TO_UNICODE_HELPER)
    if "bigint_display" in needs:
        blocks.append(_DISPLAY_DIGITS_BIG_HELPER)
    if "bigint_packed" in needs:
        blocks.append(_PACKED_DECIMAL_BIG_HELPER)
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
    base: int,
) -> str:
    """Emits this group's struct type, then recurses into its children
    (each appending its own accessor - and, for a nested group, its own
    struct type first). Returns the Go struct type name, so the caller
    (the parent group, or generate_go_decoder for the root) can use it.

    base (int): what absolute offset this group's own buf[0] corresponds
        to - see the module docstring's OCCURS section. Applies to this
        group's *children*; a plain child passes it straight through,
        an OCCURS child resets it to its own node.offset.
    """
    struct_name = go_field_name(node.name)
    struct_decls.append(f"type {struct_name} struct {{\n\tbuf []byte\n}}")
    for child in node.children:
        _render_child(
            child, f"{field_path}.{child.name}", resolved, struct_name, needs,
            struct_decls, accessor_blocks, base,
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
    base: int,
) -> None:
    if node.redefines is not None:
        raise UnsupportedDecodeError(
            f"go decoder: REDEFINES field {node.name!r} isn't supported yet"
        )

    method_name = go_field_name(node.name)

    if node.pic is None and node.children:
        child_base = node.offset if node.occurs is not None else base
        child_struct_name = _render_group(
            node, field_path, resolved, needs, struct_decls, accessor_blocks, child_base
        )
        if node.occurs is not None:
            accessor_blocks.append(
                _render_occurs_group_accessor(
                    method_name, node, base, child_struct_name, parent_struct_name
                )
            )
        else:
            accessor_blocks.append(
                f"func (r *{parent_struct_name}) {method_name}() {child_struct_name} {{\n"
                f"\treturn {child_struct_name}{{buf: r.buf}}\n"
                "}"
            )
        return

    accessor_blocks.append(
        _render_leaf_accessor(node, field_path, resolved, parent_struct_name, needs, base)
    )


def _render_occurs_group_accessor(
    method_name: str,
    node: FieldNode,
    base: int,
    child_struct_name: str,
    parent_struct_name: str,
) -> str:
    rel_start = node.offset - base
    return (
        f"func (r *{parent_struct_name}) {method_name}(index int) "
        f"({child_struct_name}, error) {{\n"
        f"\tif index < 0 || index >= {node.occurs} {{\n"
        f"\t\treturn {child_struct_name}{{}}, "
        f'fmt.Errorf("{method_name}: index %d out of range [0, {node.occurs})", index)\n'
        "\t}\n"
        f"\tstart := {rel_start} + index*{node.byte_size}\n"
        f"\treturn {child_struct_name}{{buf: r.buf[start : start+{node.byte_size}]}}, nil\n"
        "}"
    )


def _finish_two_return_leaf(
    method_name: str,
    return_type: str,
    zero_literal: str,
    node: FieldNode,
    base: int,
    body: str,
    struct_name: str,
) -> str:
    """Wraps a leaf body (already written in terms of a `raw` byte slice)
    with its accessor signature and the `raw := ...` line - adding an
    `index int` parameter and a bounds check first when node.occurs is
    set, exactly as a non-OCCURS leaf does today when it isn't. Shared
    by every leaf kind that already returns (T, error) unconditionally
    (the int ladder and big.Int); plain alphanumeric has its own version
    since its non-OCCURS form returns no error at all.
    """
    rel_start = node.offset - base
    if node.occurs is None:
        header = f"func (r *{struct_name}) {method_name}() ({return_type}, error) {{\n"
        raw_line = f"\traw := r.buf[{rel_start}:{rel_start + node.byte_size}]\n"
    else:
        header = f"func (r *{struct_name}) {method_name}(index int) ({return_type}, error) {{\n"
        raw_line = (
            f"\tif index < 0 || index >= {node.occurs} {{\n"
            f"\t\treturn {zero_literal}, "
            f'fmt.Errorf("{method_name}: index %d out of range [0, {node.occurs})", index)\n'
            "\t}\n"
            f"\tstart := {rel_start} + index*{node.byte_size}\n"
            f"\traw := r.buf[start : start+{node.byte_size}]\n"
        )
    return header + raw_line + body + "}"


def _render_leaf_accessor(
    node: FieldNode,
    field_path: str,
    resolved: dict[str, str],
    struct_name: str,
    needs: set[str],
    base: int,
) -> str:
    if node.pic is None:
        raise UnsupportedDecodeError(
            f"go decoder: COMP-1/COMP-2 field {node.name!r} isn't supported yet"
        )
    if is_edited_pic(node.pic) or is_national_pic(node.pic):
        raise UnsupportedDecodeError(
            f"go decoder: edited/national field {node.name!r} isn't supported yet"
        )

    method_name = go_field_name(node.name)

    if is_alpha_pic(node.pic):
        # Alphanumeric fields never go through mapping's integer ladder
        # (mapping/engine.py excludes them from candidate generation),
        # so field_path has no entry in resolved - checking is_alpha_pic
        # first, before ever touching resolved[field_path], is what
        # avoids a KeyError here.
        needs.add("alpha")
        return _render_alpha_accessor(method_name, node, base, struct_name)

    resolved_type = resolved[field_path]
    # "int64 (scaled)" is decision 0002's marker for a scaled decimal
    # field - the Go type is plain int64; the caller already knows the
    # scale from the DSL/report (same convention generate_go() uses).
    go_type = "int64" if resolved_type == "int64 (scaled)" else resolved_type
    if go_type != _BIG_INT_GO_TYPE and go_type not in _INTEGER_GO_TYPES:
        raise UnsupportedDecodeError(
            f"go decoder: resolved type {resolved_type!r} for {field_path!r} isn't "
            "supported in this slice (only int8..int64/uint8..uint64/big.Int, or a "
            "scaled int64)"
        )

    if go_type == _BIG_INT_GO_TYPE:
        return _render_bigint_leaf_accessor(node, method_name, struct_name, needs, base)

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

    return _finish_two_return_leaf(method_name, go_type, "0", node, base, body, struct_name)


def _render_alpha_accessor(method_name: str, node: FieldNode, base: int, struct_name: str) -> str:
    # No error return in the non-OCCURS case: the cp037 table is total
    # (every byte in 0-255 maps to something), so unlike the
    # digit-validating DISPLAY/packed bodies, there's nothing to fail
    # on - except the OCCURS index itself, which is why the OCCURS form
    # below gains an error return the plain form doesn't need.
    rel_start = node.offset - base
    if node.occurs is None:
        return (
            f"func (r *{struct_name}) {method_name}() string {{\n"
            f"\traw := r.buf[{rel_start}:{rel_start + node.byte_size}]\n"
            "\treturn decodeAlphaCP037(raw)\n"
            "}"
        )
    return (
        f"func (r *{struct_name}) {method_name}(index int) (string, error) {{\n"
        f"\tif index < 0 || index >= {node.occurs} {{\n"
        f'\t\treturn "", fmt.Errorf("{method_name}: index %d out of range '
        f'[0, {node.occurs})", index)\n'
        "\t}\n"
        f"\tstart := {rel_start} + index*{node.byte_size}\n"
        f"\traw := r.buf[start : start+{node.byte_size}]\n"
        "\treturn decodeAlphaCP037(raw), nil\n"
        "}"
    )


def _render_bigint_leaf_accessor(
    node: FieldNode,
    method_name: str,
    struct_name: str,
    needs: set[str],
    base: int,
) -> str:
    needs.add("bigint")
    if is_packed_usage(node.usage):
        needs.add("bigint_packed")
        body = _packed_body_big(method_name, node.digits)
    elif node.usage.upper() == "DISPLAY":
        needs.add("bigint_display")
        if not node.signed:
            body = _unsigned_display_body_big(method_name)
        elif node.sign_separate:
            body = _separate_sign_display_body_big(method_name, node.sign_leading)
        elif node.sign_leading:
            body = _leading_overpunch_display_body_big(method_name)
        else:
            body = _signed_display_body_big(method_name)
    else:
        raise UnsupportedDecodeError(
            f"go decoder: big.Int is only supported for DISPLAY/COMP-3 fields in this "
            f"slice, got {node.usage!r} for {node.name!r}"
        )

    return _finish_two_return_leaf(method_name, "*big.Int", "nil", node, base, body, struct_name)


def _unsigned_display_body_big(method_name: str) -> str:
    return (
        "\tv, err := decodeDisplayDigitsBig(raw)\n"
        "\tif err != nil {\n"
        f'\t\treturn nil, fmt.Errorf("{method_name}: %w", err)\n'
        "\t}\n"
        "\treturn v, nil\n"
    )


def _signed_display_body_big(method_name: str) -> str:
    return (
        "\tlead := raw[:len(raw)-1]\n"
        "\tlast := raw[len(raw)-1]\n"
        "\tv, err := decodeDisplayDigitsBig(lead)\n"
        "\tif err != nil {\n"
        f'\t\treturn nil, fmt.Errorf("{method_name}: %w", err)\n'
        "\t}\n"
        "\tzone := last & 0xF0\n"
        "\tdigit := last & 0x0F\n"
        "\tif digit > 9 {\n"
        f'\t\treturn nil, fmt.Errorf("{method_name}: last byte %#02x has a non-digit value '
        'nibble %d", last, digit)\n'
        "\t}\n"
        "\tv.Mul(v, big.NewInt(10))\n"
        "\tv.Add(v, big.NewInt(int64(digit)))\n"
        "\tswitch zone {\n"
        "\tcase 0xC0, 0xF0:\n"
        "\t\t// positive\n"
        "\tcase 0xD0:\n"
        "\t\tv.Neg(v)\n"
        "\tdefault:\n"
        f'\t\treturn nil, fmt.Errorf("{method_name}: last byte %#02x has an unrecognized sign '
        'nibble %#02x", last, zone)\n'
        "\t}\n"
        "\treturn v, nil\n"
    )


def _leading_overpunch_display_body_big(method_name: str) -> str:
    return (
        "\tfirst := raw[0]\n"
        "\trest := raw[1:]\n"
        "\tzone := first & 0xF0\n"
        "\tdigit := first & 0x0F\n"
        "\tif digit > 9 {\n"
        f'\t\treturn nil, fmt.Errorf("{method_name}: first byte %#02x has a non-digit value '
        'nibble %d", first, digit)\n'
        "\t}\n"
        "\ttail, err := decodeDisplayDigitsBig(rest)\n"
        "\tif err != nil {\n"
        f'\t\treturn nil, fmt.Errorf("{method_name}: %w", err)\n'
        "\t}\n"
        "\tscale := new(big.Int).Exp(big.NewInt(10), big.NewInt(int64(len(rest))), nil)\n"
        "\tv := new(big.Int).Mul(big.NewInt(int64(digit)), scale)\n"
        "\tv.Add(v, tail)\n"
        "\tswitch zone {\n"
        "\tcase 0xC0, 0xF0:\n"
        "\t\t// positive\n"
        "\tcase 0xD0:\n"
        "\t\tv.Neg(v)\n"
        "\tdefault:\n"
        f'\t\treturn nil, fmt.Errorf("{method_name}: first byte %#02x has an unrecognized sign '
        'nibble %#02x", first, zone)\n'
        "\t}\n"
        "\treturn v, nil\n"
    )


def _separate_sign_display_body_big(method_name: str, sign_leading: bool) -> str:
    split = (
        "sign, digits := raw[0], raw[1:]"
        if sign_leading
        else "digits, sign := raw[:len(raw)-1], raw[len(raw)-1]"
    )
    return (
        f"\t{split}\n"
        "\tv, err := decodeDisplayDigitsBig(digits)\n"
        "\tif err != nil {\n"
        f'\t\treturn nil, fmt.Errorf("{method_name}: %w", err)\n'
        "\t}\n"
        "\tswitch sign {\n"
        "\tcase 0x4E: // '+' (cp037)\n"
        "\t\treturn v, nil\n"
        "\tcase 0x60: // '-' (cp037)\n"
        "\t\tv.Neg(v)\n"
        "\t\treturn v, nil\n"
        "\tdefault:\n"
        f'\t\treturn nil, fmt.Errorf("{method_name}: separate sign byte %#02x is not \'+\' or '
        '\'-\'", sign)\n'
        "\t}\n"
    )


def _packed_body_big(method_name: str, digits: int) -> str:
    return (
        f"\tv, err := decodePackedDecimalBig(raw, {digits})\n"
        "\tif err != nil {\n"
        f'\t\treturn nil, fmt.Errorf("{method_name}: %w", err)\n'
        "\t}\n"
        "\treturn v, nil\n"
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

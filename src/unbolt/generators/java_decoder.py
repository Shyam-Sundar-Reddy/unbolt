"""Java flyweight decoder generation (ADR 0009): fixed-offset accessor
methods reading directly from a ByteBuffer - zero reflection, and no
heap allocation for leaf access (only a nested-group accessor call
allocates a small object, since Java has no value-type struct the way
Go does - a real, documented difference from the Go decoder, not
hidden). A different artifact from generate_java()'s POJOs, not a
replacement for it - decision 0006 stays untouched.

First slice, scoped as narrowly as the Go decoder's own first slice
was: one class per DSL root (Java requires one public top-level type
per file anyway, same reason generate_java() already returns
dict[str, str] rather than one blob - reused here unchanged), flat
records only (no nested groups/OCCURS/REDEFINES yet). Current scope,
after the second slice below: DISPLAY (unsigned + signed trailing
overpunch - no SIGN IS SEPARATE/LEADING yet), COMP-3/PACKED-DECIMAL,
and COMP/COMP-4/COMP-5/BINARY leaf fields; and only the plain
byte/short/int/long integer-ladder Java types (no BigInteger/
BigDecimal/String yet - decision 0004's default candidate resolution
never picks those for a plain integer field anyway, but a forced
override could, and a decimal/scaled field always resolves to
BigDecimal for Java - construction from an unscaled BigInteger + scale
is a real, separate design question, not decided here). Later slices
lift the remaining restrictions one at a time, mirroring exactly how
go_decoder.py's own eight slices were sequenced.

A ByteBuffer's absolute indexed getters (get(int), getInt(int), ...)
read without touching position/mark state, and default to big-endian
byte order - exactly COBOL's own big-endian convention - so, unlike
Go's []byte slices, nothing here will ever need to reslice a buffer:
every accessor can just read directly from the one ByteBuffer the
record was constructed with, at a plain absolute int index. (Nested
groups and OCCURS, once in scope, will still need a small per-instance
`base` field to track "what absolute index does this view's own
offset 0 correspond to" - Go gets the equivalent fact for free from
slicing; Java pays for it with one int field per instance instead.
Deferred to the slice that actually introduces nested groups.)

Decode errors throw java.lang.IllegalArgumentException (unchecked) -
reusing generate_java()'s own precedent for its range validators,
rather than inventing a new checked-exception type generated code's
consumers would have to declare or catch explicitly.

Second slice: COMP-3/PACKED-DECIMAL and COMP/COMP-4/COMP-5/BINARY,
mirroring go_decoder.py's own second slice exactly - no new design
question turned up porting it. COMP-3 decodes via a private static
decodePackedDecimal(buf, start, end, digits) helper, emitted once per
class, only when a packed field exists on that root (mirrors Go's own
"needs" + shared-helper pattern, one class = one file = Go's own "one
file" scope for that pattern). BINARY fields read via ByteBuffer's own
getShort/getInt/getLong(int) - already big-endian by default, so no
encoding/binary-style explicit byte-order setup is needed the way Go's
own encoding/binary import was. Java has no unsigned primitives
(java_rules.py's own ladder already reflects this - checked, not
assumed), so an unsigned field's resolved type is always wide enough
that the *next* unsigned-correct step is a mask-and-widen
(`raw & 0xFFFF` for 2 bytes, `raw & 0xFFFFFFFFL` for 4 - the mask's
own width has to match or exceed the target type for the widening
promotion to produce the right unsigned value) rather than Go's
"read natively unsigned via encoding/binary, no masking needed" shape.
An unsigned 8-byte BINARY field is never reachable here: its full
range always exceeds `long`'s own signed range, so the ladder already
resolves it to BigInteger, which the existing type check rejects
before any binary-specific logic runs.
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
from unbolt.generators.naming import go_field_name, java_field_name

_INTEGER_JAVA_TYPES = frozenset({"byte", "short", "int", "long"})
_BINARY_WIDTH_READER = {2: "getShort", 4: "getInt", 8: "getLong"}
_BINARY_NATIVE_TYPE = {2: "short", 4: "int", 8: "long"}
_UNSIGNED_WIDEN_MASK = {2: "0xFFFF", 4: "0xFFFFFFFFL"}

_PACKED_DECIMAL_HELPER = """private static long decodePackedDecimal(
        java.nio.ByteBuffer buf, int start, int end, int digits) {
    int totalNibbles = (end - start) * 2;
    int pad = totalNibbles - 1 - digits;
    long v = 0;
    int nibbleIndex = 0;
    for (int pos = start; pos < end; pos++) {
        int b = buf.get(pos) & 0xFF;

        int hi = b >> 4;
        if (nibbleIndex == totalNibbles - 1) {
            if (hi == 0xC || hi == 0xF) {
                // positive
            } else if (hi == 0xD) {
                v = -v;
            } else {
                throw new IllegalArgumentException(
                    "packed decimal: unrecognized sign nibble " + String.format("0x%X", hi));
            }
        } else if (nibbleIndex < pad) {
            if (hi != 0) {
                throw new IllegalArgumentException(
                    "packed decimal: non-zero leading pad nibble " + String.format("0x%X", hi));
            }
        } else {
            if (hi > 9) {
                throw new IllegalArgumentException(
                    "packed decimal: non-digit nibble " + String.format("0x%X", hi));
            }
            v = v * 10 + hi;
        }
        nibbleIndex++;

        int lo = b & 0x0F;
        if (nibbleIndex == totalNibbles - 1) {
            if (lo == 0xC || lo == 0xF) {
                // positive
            } else if (lo == 0xD) {
                v = -v;
            } else {
                throw new IllegalArgumentException(
                    "packed decimal: unrecognized sign nibble " + String.format("0x%X", lo));
            }
        } else if (nibbleIndex < pad) {
            if (lo != 0) {
                throw new IllegalArgumentException(
                    "packed decimal: non-zero leading pad nibble " + String.format("0x%X", lo));
            }
        } else {
            if (lo > 9) {
                throw new IllegalArgumentException(
                    "packed decimal: non-digit nibble " + String.format("0x%X", lo));
            }
            v = v * 10 + lo;
        }
        nibbleIndex++;
    }
    return v;
}"""


def generate_java_decoder(dsl: Dsl, resolved: dict[str, str]) -> dict[str, str]:
    """Emit a flyweight Java decoder: one public class per DSL root,
    each wrapping a java.nio.ByteBuffer, with one getter per field
    reading directly from the buffer.

    Args: dsl (Dsl): every root must be a group (not a scalar 77-level
            item); every field under it must use a supported usage -
            this slice's scope (see module docstring).
        resolved (dict[str, str]): field_path -> Java type name, from
            generators.resolve_mapping() (the same input generate_java()
            takes) - the flyweight decoder returns the identical Java
            type the plain POJO generator would have chosen.
    Returns: dict[str, str]: {ClassName: source}, one compilation unit
        per DSL root (Java allows only one public top-level type per
        file - the same reason generate_java() returns this shape).
    Raises:
        UnsupportedDecodeError: a root or field is outside this
            slice's scope (see module docstring).
    Example:
        >>> from unbolt.dsl import build_dsl
        >>> from unbolt.mapping import recommend_mappings
        >>> from unbolt.generators import resolve_mapping
        >>> from unbolt.overrides import Overrides
        >>> from unbolt.parser import parse_copybook
        >>> dsl = build_dsl(parse_copybook("01 X.\\n  05 A PIC 9(3)."), source_file="<t>")
        >>> resolved = resolve_mapping(recommend_mappings(dsl, "java"), Overrides())
        >>> "public short getA()" in generate_java_decoder(dsl, resolved)["X"]
        True
    """
    return {
        go_field_name(root.name): _render_root(root, root.name, resolved) for root in dsl.roots
    }


def _render_root(root: FieldNode, field_path: str, resolved: dict[str, str]) -> str:
    if root.pic is not None or not root.children:
        raise UnsupportedDecodeError(
            f"java decoder: root {root.name!r} must be a group in this slice"
        )

    class_name = go_field_name(root.name)
    needs: set[str] = set()
    accessor_blocks = [
        _render_leaf_accessor(child, f"{field_path}.{child.name}", resolved, needs)
        for child in root.children
    ]

    lines = [
        f"public class {class_name} {{",
        "    private final java.nio.ByteBuffer buf;",
        "",
        f"    public {class_name}(java.nio.ByteBuffer buf) {{",
        f"        if (buf.capacity() != {root.byte_size}) {{",
        f'            throw new IllegalArgumentException("{class_name}: expected '
        f'{root.byte_size} bytes, got " + buf.capacity());',
        "        }",
        "        this.buf = buf;",
        "    }",
    ]
    for block in accessor_blocks:
        lines.append("")
        lines.extend(f"    {line}" if line else "" for line in block.splitlines())
    if "packed" in needs:
        lines.append("")
        lines.extend(f"    {line}" if line else "" for line in _PACKED_DECIMAL_HELPER.splitlines())
    lines.append("}")
    return "\n".join(lines) + "\n"


def _render_leaf_accessor(
    node: FieldNode, field_path: str, resolved: dict[str, str], needs: set[str]
) -> str:
    if node.occurs is not None:
        raise UnsupportedDecodeError(
            f"java decoder: OCCURS field {node.name!r} isn't supported yet"
        )
    if node.redefines is not None:
        raise UnsupportedDecodeError(
            f"java decoder: REDEFINES field {node.name!r} isn't supported yet"
        )
    if node.pic is None and node.children:
        raise UnsupportedDecodeError(
            f"java decoder: nested group field {node.name!r} isn't supported yet"
        )
    if node.pic is None:
        raise UnsupportedDecodeError(
            f"java decoder: COMP-1/COMP-2 field {node.name!r} isn't supported yet"
        )
    if is_alpha_pic(node.pic) or is_edited_pic(node.pic) or is_national_pic(node.pic):
        raise UnsupportedDecodeError(
            f"java decoder: alphanumeric/edited/national field {node.name!r} isn't supported yet"
        )

    java_type = resolved[field_path]
    if java_type not in _INTEGER_JAVA_TYPES:
        raise UnsupportedDecodeError(
            f"java decoder: resolved type {java_type!r} for {field_path!r} isn't supported "
            "in this slice (only byte/short/int/long)"
        )

    method_name, _ = java_field_name(node.name, source_line=node.source_line)
    getter_name = f"get{method_name[0].upper()}{method_name[1:]}"
    start, end = node.offset, node.offset + node.byte_size

    if is_packed_usage(node.usage):
        needs.add("packed")
        body = _packed_body(start, end, node.digits, java_type)
    elif is_binary_usage(node.usage):
        body = _binary_body(start, node.byte_size, node.signed, java_type)
    elif node.usage.upper() == "DISPLAY":
        if node.sign_separate or node.sign_leading:
            raise UnsupportedDecodeError(
                f"java decoder: SIGN IS SEPARATE/LEADING on {node.name!r} isn't supported yet"
            )
        if not node.signed:
            body = _unsigned_display_body(node.name, start, end, java_type)
        else:
            body = _signed_display_body(node.name, start, end, java_type)
    else:
        raise UnsupportedDecodeError(
            f"java decoder: only DISPLAY/COMP-3/binary fields are supported in this "
            f"slice, got {node.usage!r} for {node.name!r}"
        )

    return f"public {java_type} {getter_name}() {{\n" + body + "}"


def _unsigned_display_body(field_label: str, start: int, end: int, java_type: str) -> str:
    return (
        "    long v = 0;\n"
        f"    for (int i = {start}; i < {end}; i++) {{\n"
        "        int b = buf.get(i) & 0xFF;\n"
        "        if (b < 0xF0 || b > 0xF9) {\n"
        f'            throw new IllegalArgumentException("{field_label}: byte " + '
        'String.format("0x%02X", b) + " is not a DISPLAY digit");\n'
        "        }\n"
        "        v = v * 10 + (b & 0x0F);\n"
        "    }\n"
        f"    return ({java_type}) v;\n"
    )


def _signed_display_body(field_label: str, start: int, end: int, java_type: str) -> str:
    return (
        "    long v = 0;\n"
        f"    for (int i = {start}; i < {end - 1}; i++) {{\n"
        "        int b = buf.get(i) & 0xFF;\n"
        "        if (b < 0xF0 || b > 0xF9) {\n"
        f'            throw new IllegalArgumentException("{field_label}: byte " + '
        'String.format("0x%02X", b) + " is not a DISPLAY digit");\n'
        "        }\n"
        "        v = v * 10 + (b & 0x0F);\n"
        "    }\n"
        f"    int last = buf.get({end - 1}) & 0xFF;\n"
        "    int zone = last & 0xF0;\n"
        "    int digit = last & 0x0F;\n"
        "    if (digit > 9) {\n"
        f'        throw new IllegalArgumentException("{field_label}: last byte " + '
        'String.format("0x%02X", last) + " has a non-digit value nibble " + digit);\n'
        "    }\n"
        "    v = v * 10 + digit;\n"
        "    switch (zone) {\n"
        "        case 0xC0:\n"
        "        case 0xF0:\n"
        "            break;\n"
        "        case 0xD0:\n"
        "            v = -v;\n"
        "            break;\n"
        "        default:\n"
        f'            throw new IllegalArgumentException("{field_label}: last byte " + '
        'String.format("0x%02X", last) + " has an unrecognized sign nibble " + '
        'String.format("0x%02X", zone));\n'
        "    }\n"
        f"    return ({java_type}) v;\n"
    )


def _packed_body(start: int, end: int, digits: int, java_type: str) -> str:
    return (
        f"    long v = decodePackedDecimal(buf, {start}, {end}, {digits});\n"
        f"    return ({java_type}) v;\n"
    )


def _binary_body(start: int, byte_size: int, signed: bool, java_type: str) -> str:
    reader = _BINARY_WIDTH_READER[byte_size]
    native_type = _BINARY_NATIVE_TYPE[byte_size]
    # Java has no unsigned primitives, so an unsigned field's resolved
    # type has to be wide enough to hold the full unsigned range - the
    # mask widens the native signed read into that correct unsigned
    # value. No mask for an unsigned 8-byte field: its digit ceiling
    # (18, datatypes/sizing.py's own BINARY tier limit) means its max
    # value (999999999999999999) always fits within `long`'s own
    # signed range (9223372036854775807) - confirmed by computing
    # both, not assumed - so there's no wider type to widen into and
    # none is needed; the native getLong() read is already correct.
    mask = None if signed else _UNSIGNED_WIDEN_MASK.get(byte_size)
    if mask is None:
        return (
            f"    {native_type} raw = buf.{reader}({start});\n"
            f"    return ({java_type}) raw;\n"
        )
    return (
        f"    {native_type} raw = buf.{reader}({start});\n"
        f"    return ({java_type}) (raw & {mask});\n"
    )

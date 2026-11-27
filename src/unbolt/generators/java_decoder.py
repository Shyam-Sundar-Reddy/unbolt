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
record was constructed with, at a plain absolute int index. A plain
nested group's position is fully known at codegen time (no runtime
index is involved), so it needs no per-instance state at all - the
same absolute-offset literals a flat record already uses work
unchanged at any nesting depth. OCCURS, once in scope, is the one
case that will genuinely need a small per-instance `base` field, to
track "what absolute index does this occurrence's own offset 0
correspond to" once a runtime index can shift it - Go gets the
equivalent fact for free from slicing; Java will pay for it with one
int field per instance instead. Deferred to the slice that actually
introduces OCCURS.

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
(`raw & 0xFFFF` for 2 bytes, `raw & 0xFFFFFFFFL` for 4) - except an
unsigned 8-byte field, which needs no mask at all: its 18-digit
ceiling (datatypes/sizing.py's own BINARY tier limit) always fits
within long's own signed range (999999999999999999 <
9223372036854775807, confirmed by computing both, not assumed), so
there's no wider type to widen into. An earlier version of this code
got that backwards - assumed the unsigned 8-byte case needed the same
masking pattern one step further and had no mask entry for it at all,
raising KeyError the moment it was actually run - caught and fixed by
a real round-trip test, exactly the discipline those tests exist for.

Third slice: nested groups, mirroring go_decoder.py's own third slice.
A nested group gets its own public static class, textually nested
inside its parent (mirroring generate_java()'s own nested-static-class
shape, since Java has no floating top-level static class the way Go's
flat top-level types allow), with an accessor on the parent returning
a fresh instance sharing the same buf - one small heap allocation per
call, unlike Go's zero-allocation struct values (the real,
documented difference this module's own opening paragraph already
names). No base field needed yet, as explained above.

Fourth slice: SIGN IS SEPARATE/LEADING, mirroring go_decoder.py's own
fourth slice - leading overpunch and both separate-sign forms get
their own body generator, same as Go's.

Fifth slice: BigInteger/wider types, mirroring go_decoder.py's own
fifth slice. Reachable the same way Go's big.Int is: never decision
0004's default (java_rules.py's own ladder tops out at long before
BigInteger), but reachable past long's ~19-digit range, or via a
forced override. Shared helpers (decodeDisplayDigitsBig,
decodePackedDecimalBig) use java.math.BigInteger - immutable, unlike
Go's mutable big.Int, so every operation reassigns `v` instead of
mutating it in place, but the arithmetic itself is an unchanged port.
One genuine simplification over Go here: a helper that hits bad input
just throws IllegalArgumentException directly (unchecked) and lets it
propagate - there's no Go-style explicit (value, error) return to
thread back up through every caller, so every BigInteger accessor's
body is a single expression or a short switch, never an explicit
error check. BINARY never needs BigInteger, for the exact same reason
established in the second slice above (every BINARY tier's digit
ceiling already fits within its own native signed type) - a forced
BigInteger override on a binary field still raises rather than
guessing.
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
_BIG_INTEGER_JAVA_TYPE = "BigInteger"
_BINARY_WIDTH_READER = {2: "getShort", 4: "getInt", 8: "getLong"}
_BINARY_NATIVE_TYPE = {2: "short", 4: "int", 8: "long"}
_UNSIGNED_WIDEN_MASK = {2: "0xFFFF", 4: "0xFFFFFFFFL"}

_DISPLAY_DIGITS_BIG_HELPER = """private static java.math.BigInteger decodeDisplayDigitsBig(
        java.nio.ByteBuffer buf, int start, int end) {
    java.math.BigInteger v = java.math.BigInteger.ZERO;
    java.math.BigInteger ten = java.math.BigInteger.TEN;
    for (int i = start; i < end; i++) {
        int b = buf.get(i) & 0xFF;
        if (b < 0xF0 || b > 0xF9) {
            throw new IllegalArgumentException(
                "byte " + String.format("0x%02X", b) + " is not a DISPLAY digit");
        }
        v = v.multiply(ten).add(java.math.BigInteger.valueOf(b & 0x0F));
    }
    return v;
}"""

_PACKED_DECIMAL_BIG_HELPER = """private static java.math.BigInteger decodePackedDecimalBig(
        java.nio.ByteBuffer buf, int start, int end, int digits) {
    int totalNibbles = (end - start) * 2;
    int pad = totalNibbles - 1 - digits;
    java.math.BigInteger v = java.math.BigInteger.ZERO;
    java.math.BigInteger ten = java.math.BigInteger.TEN;
    boolean negative = false;
    int nibbleIndex = 0;
    for (int pos = start; pos < end; pos++) {
        int b = buf.get(pos) & 0xFF;

        int hi = b >> 4;
        if (nibbleIndex == totalNibbles - 1) {
            if (hi == 0xC || hi == 0xF) {
                // positive
            } else if (hi == 0xD) {
                negative = true;
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
            v = v.multiply(ten).add(java.math.BigInteger.valueOf(hi));
        }
        nibbleIndex++;

        int lo = b & 0x0F;
        if (nibbleIndex == totalNibbles - 1) {
            if (lo == 0xC || lo == 0xF) {
                // positive
            } else if (lo == 0xD) {
                negative = true;
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
            v = v.multiply(ten).add(java.math.BigInteger.valueOf(lo));
        }
        nibbleIndex++;
    }
    if (negative) {
        v = v.negate();
    }
    return v;
}"""

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
    result: dict[str, str] = {}
    for root in dsl.roots:
        if root.pic is not None or not root.children:
            raise UnsupportedDecodeError(
                f"java decoder: root {root.name!r} must be a group in this slice"
            )
        needs: set[str] = set()
        body = _render_class(root, root.name, resolved, needs, top_level=True)
        helpers = []
        if "packed" in needs:
            helpers.append(_PACKED_DECIMAL_HELPER)
        if "bigint_display" in needs:
            helpers.append(_DISPLAY_DIGITS_BIG_HELPER)
        if "bigint_packed" in needs:
            helpers.append(_PACKED_DECIMAL_BIG_HELPER)
        if helpers:
            lines = body.splitlines()
            closing_brace = lines.pop()
            for helper in helpers:
                lines.append("")
                lines.extend(f"    {line}" if line else "" for line in helper.splitlines())
            lines.append(closing_brace)
            body = "\n".join(lines)
        result[go_field_name(root.name)] = body + "\n"
    return result


def _render_class(
    node: FieldNode,
    field_path: str,
    resolved: dict[str, str],
    needs: set[str],
    *,
    top_level: bool,
) -> str:
    """Emits one class (the root, or a nested group) - its own
    constructor, one accessor per leaf field, and, for a nested-group
    child, its own class textually nested inside this one (Java has no
    floating top-level `static class`, unlike Go's flat top-level
    types - mirrors generate_java()'s own nested-static-class shape
    for exactly that reason) plus an accessor returning a fresh
    instance sharing the same buffer (one small allocation per call -
    a real, documented difference from Go's zero-allocation struct
    values, since Java has no equivalent value type).
    """
    class_name = go_field_name(node.name)
    keyword = "public class" if top_level else "public static class"

    accessor_blocks: list[str] = []
    nested_bodies: list[str] = []
    for child in node.children:
        if child.occurs is not None:
            raise UnsupportedDecodeError(
                f"java decoder: OCCURS field {child.name!r} isn't supported yet"
            )
        if child.redefines is not None:
            raise UnsupportedDecodeError(
                f"java decoder: REDEFINES field {child.name!r} isn't supported yet"
            )
        child_path = f"{field_path}.{child.name}"
        if child.pic is None and child.children:
            child_class_name = go_field_name(child.name)
            nested_bodies.append(_render_class(child, child_path, resolved, needs, top_level=False))
            method_name, _ = java_field_name(child.name, source_line=child.source_line)
            getter_name = f"get{method_name[0].upper()}{method_name[1:]}"
            accessor_blocks.append(
                f"public {child_class_name} {getter_name}() {{\n"
                f"    return new {child_class_name}(buf);\n"
                "}"
            )
            continue
        accessor_blocks.append(_render_leaf_accessor(child, child_path, resolved, needs))

    lines = [f"{keyword} {class_name} {{", "    private final java.nio.ByteBuffer buf;", ""]
    if top_level:
        lines += [
            f"    public {class_name}(java.nio.ByteBuffer buf) {{",
            f"        if (buf.capacity() != {node.byte_size}) {{",
            f'            throw new IllegalArgumentException("{class_name}: expected '
            f'{node.byte_size} bytes, got " + buf.capacity());',
            "        }",
            "        this.buf = buf;",
            "    }",
        ]
    else:
        lines += [
            f"    {class_name}(java.nio.ByteBuffer buf) {{",
            "        this.buf = buf;",
            "    }",
        ]
    for block in accessor_blocks:
        lines.append("")
        lines.extend(f"    {line}" if line else "" for line in block.splitlines())
    for nested in nested_bodies:
        lines.append("")
        lines.extend(f"    {line}" if line else "" for line in nested.splitlines())
    lines.append("}")
    return "\n".join(lines)


def _render_leaf_accessor(
    node: FieldNode, field_path: str, resolved: dict[str, str], needs: set[str]
) -> str:
    if node.pic is None:
        raise UnsupportedDecodeError(
            f"java decoder: COMP-1/COMP-2 field {node.name!r} isn't supported yet"
        )
    if is_alpha_pic(node.pic) or is_edited_pic(node.pic) or is_national_pic(node.pic):
        raise UnsupportedDecodeError(
            f"java decoder: alphanumeric/edited/national field {node.name!r} isn't supported yet"
        )

    java_type = resolved[field_path]
    if java_type != _BIG_INTEGER_JAVA_TYPE and java_type not in _INTEGER_JAVA_TYPES:
        raise UnsupportedDecodeError(
            f"java decoder: resolved type {java_type!r} for {field_path!r} isn't supported "
            "in this slice (only byte/short/int/long/BigInteger)"
        )

    method_name, _ = java_field_name(node.name, source_line=node.source_line)
    getter_name = f"get{method_name[0].upper()}{method_name[1:]}"
    start, end = node.offset, node.offset + node.byte_size

    if java_type == _BIG_INTEGER_JAVA_TYPE:
        return _render_bigint_leaf_accessor(node, getter_name, start, end, needs)

    if is_packed_usage(node.usage):
        needs.add("packed")
        body = _packed_body(start, end, node.digits, java_type)
    elif is_binary_usage(node.usage):
        body = _binary_body(start, node.byte_size, node.signed, java_type)
    elif node.usage.upper() == "DISPLAY":
        if not node.signed:
            body = _unsigned_display_body(node.name, start, end, java_type)
        elif node.sign_separate:
            body = _separate_sign_display_body(
                node.name, start, end, node.sign_leading, java_type
            )
        elif node.sign_leading:
            body = _leading_overpunch_display_body(node.name, start, end, java_type)
        else:
            body = _signed_display_body(node.name, start, end, java_type)
    else:
        raise UnsupportedDecodeError(
            f"java decoder: only DISPLAY/COMP-3/binary fields are supported in this "
            f"slice, got {node.usage!r} for {node.name!r}"
        )

    return f"public {java_type} {getter_name}() {{\n" + body + "}"


def _render_bigint_leaf_accessor(
    node: FieldNode, getter_name: str, start: int, end: int, needs: set[str]
) -> str:
    if is_packed_usage(node.usage):
        needs.add("bigint_packed")
        body = _packed_body_big(start, end, node.digits)
    elif node.usage.upper() == "DISPLAY":
        needs.add("bigint_display")
        if not node.signed:
            body = _unsigned_display_body_big(start, end)
        elif node.sign_separate:
            body = _separate_sign_display_body_big(node.name, start, end, node.sign_leading)
        elif node.sign_leading:
            body = _leading_overpunch_display_body_big(node.name, start, end)
        else:
            body = _signed_display_body_big(node.name, start, end)
    else:
        raise UnsupportedDecodeError(
            f"java decoder: BigInteger is only supported for DISPLAY/COMP-3 fields in "
            f"this slice, got {node.usage!r} for {node.name!r}"
        )
    return f"public java.math.BigInteger {getter_name}() {{\n" + body + "}"


def _unsigned_display_body_big(start: int, end: int) -> str:
    return f"    return decodeDisplayDigitsBig(buf, {start}, {end});\n"


def _signed_display_body_big(field_label: str, start: int, end: int) -> str:
    return (
        f"    java.math.BigInteger v = decodeDisplayDigitsBig(buf, {start}, {end - 1});\n"
        f"    int last = buf.get({end - 1}) & 0xFF;\n"
        "    int zone = last & 0xF0;\n"
        "    int digit = last & 0x0F;\n"
        "    if (digit > 9) {\n"
        f'        throw new IllegalArgumentException("{field_label}: last byte " + '
        'String.format("0x%02X", last) + " has a non-digit value nibble " + digit);\n'
        "    }\n"
        "    v = v.multiply(java.math.BigInteger.TEN).add(java.math.BigInteger.valueOf(digit));\n"
        "    switch (zone) {\n"
        "        case 0xC0:\n"
        "        case 0xF0:\n"
        "            break;\n"
        "        case 0xD0:\n"
        "            v = v.negate();\n"
        "            break;\n"
        "        default:\n"
        f'            throw new IllegalArgumentException("{field_label}: last byte " + '
        'String.format("0x%02X", last) + " has an unrecognized sign nibble " + '
        'String.format("0x%02X", zone));\n'
        "    }\n"
        "    return v;\n"
    )


def _leading_overpunch_display_body_big(field_label: str, start: int, end: int) -> str:
    return (
        f"    int first = buf.get({start}) & 0xFF;\n"
        "    int zone = first & 0xF0;\n"
        "    int digit = first & 0x0F;\n"
        "    if (digit > 9) {\n"
        f'        throw new IllegalArgumentException("{field_label}: first byte " + '
        'String.format("0x%02X", first) + " has a non-digit value nibble " + digit);\n'
        "    }\n"
        f"    java.math.BigInteger tail = decodeDisplayDigitsBig(buf, {start + 1}, {end});\n"
        f"    java.math.BigInteger scale = java.math.BigInteger.TEN.pow({end - start - 1});\n"
        "    java.math.BigInteger v = java.math.BigInteger.valueOf(digit).multiply(scale)"
        ".add(tail);\n"
        "    switch (zone) {\n"
        "        case 0xC0:\n"
        "        case 0xF0:\n"
        "            break;\n"
        "        case 0xD0:\n"
        "            v = v.negate();\n"
        "            break;\n"
        "        default:\n"
        f'            throw new IllegalArgumentException("{field_label}: first byte " + '
        'String.format("0x%02X", first) + " has an unrecognized sign nibble " + '
        'String.format("0x%02X", zone));\n'
        "    }\n"
        "    return v;\n"
    )


def _separate_sign_display_body_big(
    field_label: str, start: int, end: int, sign_leading: bool
) -> str:
    if sign_leading:
        sign_pos, digits_start, digits_end = start, start + 1, end
    else:
        sign_pos, digits_start, digits_end = end - 1, start, end - 1
    return (
        f"    int sign = buf.get({sign_pos}) & 0xFF;\n"
        f"    java.math.BigInteger v = decodeDisplayDigitsBig(buf, {digits_start}, "
        f"{digits_end});\n"
        "    switch (sign) {\n"
        "        case 0x4E:\n"
        "            return v;\n"
        "        case 0x60:\n"
        "            return v.negate();\n"
        "        default:\n"
        f'            throw new IllegalArgumentException("{field_label}: separate sign byte " + '
        'String.format("0x%02X", sign) + " is not \'+\' or \'-\'");\n'
        "    }\n"
    )


def _packed_body_big(start: int, end: int, digits: int) -> str:
    return f"    return decodePackedDecimalBig(buf, {start}, {end}, {digits});\n"


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


def _leading_overpunch_display_body(field_label: str, start: int, end: int, java_type: str) -> str:
    return (
        f"    int first = buf.get({start}) & 0xFF;\n"
        "    int zone = first & 0xF0;\n"
        "    int digit = first & 0x0F;\n"
        "    if (digit > 9) {\n"
        f'        throw new IllegalArgumentException("{field_label}: first byte " + '
        'String.format("0x%02X", first) + " has a non-digit value nibble " + digit);\n'
        "    }\n"
        "    long v = digit;\n"
        f"    for (int i = {start + 1}; i < {end}; i++) {{\n"
        "        int b = buf.get(i) & 0xFF;\n"
        "        if (b < 0xF0 || b > 0xF9) {\n"
        f'            throw new IllegalArgumentException("{field_label}: byte " + '
        'String.format("0x%02X", b) + " is not a DISPLAY digit");\n'
        "        }\n"
        "        v = v * 10 + (b & 0x0F);\n"
        "    }\n"
        "    switch (zone) {\n"
        "        case 0xC0:\n"
        "        case 0xF0:\n"
        "            break;\n"
        "        case 0xD0:\n"
        "            v = -v;\n"
        "            break;\n"
        "        default:\n"
        f'            throw new IllegalArgumentException("{field_label}: first byte " + '
        'String.format("0x%02X", first) + " has an unrecognized sign nibble " + '
        'String.format("0x%02X", zone));\n'
        "    }\n"
        f"    return ({java_type}) v;\n"
    )


def _separate_sign_display_body(
    field_label: str, start: int, end: int, sign_leading: bool, java_type: str
) -> str:
    if sign_leading:
        sign_pos, digits_start, digits_end = start, start + 1, end
    else:
        sign_pos, digits_start, digits_end = end - 1, start, end - 1
    return (
        f"    int sign = buf.get({sign_pos}) & 0xFF;\n"
        "    long v = 0;\n"
        f"    for (int i = {digits_start}; i < {digits_end}; i++) {{\n"
        "        int b = buf.get(i) & 0xFF;\n"
        "        if (b < 0xF0 || b > 0xF9) {\n"
        f'            throw new IllegalArgumentException("{field_label}: byte " + '
        'String.format("0x%02X", b) + " is not a DISPLAY digit");\n'
        "        }\n"
        "        v = v * 10 + (b & 0x0F);\n"
        "    }\n"
        "    switch (sign) {\n"
        "        case 0x4E:\n"
        f"            return ({java_type}) v;\n"
        "        case 0x60:\n"
        f"            return ({java_type}) (-v);\n"
        "        default:\n"
        f'            throw new IllegalArgumentException("{field_label}: separate sign byte " + '
        'String.format("0x%02X", sign) + " is not \'+\' or \'-\'");\n'
        "    }\n"
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

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
records only (no nested groups/OCCURS/REDEFINES yet), DISPLAY fields
only (unsigned + signed trailing overpunch - no SIGN IS SEPARATE/
LEADING yet), and only the plain byte/short/int/long integer-ladder
Java types (no BigInteger/BigDecimal/String yet - decision 0004's
default candidate resolution never picks those for a plain integer
field anyway, but a forced override could, and a decimal/scaled field
always resolves to BigDecimal for Java - construction from an
unscaled BigInteger + scale is a real, separate design question, not
decided here). Later slices lift these restrictions one at a time,
mirroring exactly how go_decoder.py's own eight slices were sequenced.

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
"""

from unbolt.datatypes.sizing import is_alpha_pic, is_edited_pic, is_national_pic
from unbolt.dsl.schema import Dsl, FieldNode
from unbolt.exceptions import UnsupportedDecodeError
from unbolt.generators.naming import go_field_name, java_field_name

_INTEGER_JAVA_TYPES = frozenset({"byte", "short", "int", "long"})
_WIDENING_CAST = {"byte": "byte", "short": "short", "int": "int", "long": "long"}


def generate_java_decoder(dsl: Dsl, resolved: dict[str, str]) -> dict[str, str]:
    """Emit a flyweight Java decoder: one public class per DSL root,
    each wrapping a java.nio.ByteBuffer, with one getter per field
    reading directly from the buffer.

    Args: dsl (Dsl): every root must be a group (not a scalar 77-level
            item); every field under it must be a supported DISPLAY
            field - this slice's scope (see module docstring).
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
    accessor_blocks = [
        _render_leaf_accessor(child, f"{field_path}.{child.name}", resolved)
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
    lines.append("}")
    return "\n".join(lines) + "\n"


def _render_leaf_accessor(node: FieldNode, field_path: str, resolved: dict[str, str]) -> str:
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
    if node.usage.upper() != "DISPLAY":
        raise UnsupportedDecodeError(
            f"java decoder: only DISPLAY fields are supported in this slice, got "
            f"{node.usage!r} for {node.name!r}"
        )
    if node.sign_separate or node.sign_leading:
        raise UnsupportedDecodeError(
            f"java decoder: SIGN IS SEPARATE/LEADING on {node.name!r} isn't supported yet"
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

    if not node.signed:
        body = _unsigned_display_body(node.name, start, end)
    else:
        body = _signed_display_body(node.name, start, end)

    cast = _WIDENING_CAST[java_type]
    return (
        f"public {java_type} {getter_name}() {{\n" + body + f"    return ({cast}) v;\n" "}"
    )


def _unsigned_display_body(field_label: str, start: int, end: int) -> str:
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
    )


def _signed_display_body(field_label: str, start: int, end: int) -> str:
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
    )

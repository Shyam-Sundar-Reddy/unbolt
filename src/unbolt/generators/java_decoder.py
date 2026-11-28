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

Sixth slice: plain alphanumeric (PIC X/A) decode. Unlike Go, which
has no EBCDIC codec in its standard library at all (go_decoder.py
hardcodes a 256-entry cp037 table for exactly that reason), Java's
standard library ships "Cp037" as a real Charset
(Charset.forName("Cp037"), resolving to "IBM037") - confirmed by
actually running it in a real JDK 21 container and checking its
output against decode_alpha()'s own doctest value, not assumed from
the name alone. So this slice needs no table and no dependency
decision at all: a shared `private static final Charset CP037 =
Charset.forName("Cp037");` field (emitted once per class, only when
an alphanumeric field exists), and each accessor copies its own bytes
into a small byte[] (ByteBuffer has no absolute bulk-get on every
JDK version, so this is a plain loop, not a bulk API call) and
decodes it with `new String(bytes, CP037)`. Returns the exact
fixed-width, space-padded text, matching decode_alpha()'s own default
(no silent trailing-space stripping).

Seventh slice: OCCURS, mirroring go_decoder.py's own seventh slice -
leaf and group, one mechanism, same reasoning for doing both in one
slice. This is the slice the third slice's own docstring predicted
would need a per-instance `base` field, now built: every class that
is ever reached through an OCCURS group gains a `private final int
base` field (via a package-private `(ByteBuffer buf, int base)`
constructor) meaning "what absolute index does this instance's own
offset 0 correspond to" - `null`/absent everywhere else, so a class
never reached through OCCURS keeps today's bare-absolute-offset
scheme, unchanged, exactly as the third slice already established for
plain nested groups. Entering an OCCURS group's children resets this
to that group's own `node.offset`, however deep; a plain nested group
passes whatever `base` it received straight through.

Where Go's OCCURS slice needed zero runtime state (a reslice already
puts byte 0 of a new slice at the right place), Java's `base` field
*is* runtime state, because Java accessors never reslice - every
accessor computes `int start = (this.base, if any) + <offset relative
to the enclosing OCCURS group, baked as a literal> (+ index *
byte_size, for the field's own OCCURS)`. That `start`/`end` pair is
unknown at codegen time whenever a runtime index is in play, so every
DISPLAY sign-placement body that does its own offset arithmetic
(signed trailing overpunch, leading overpunch, either SIGN IS
SEPARATE form) needed a *second*, parallel body generator - one
written in terms of the literal int offsets (today's, untouched, so
existing non-OCCURS output stays byte-for-byte identical), one
written in terms of the `start`/`end` *local Java variables* the new
preamble declares, doing its arithmetic as ordinary Java expressions
(`end - 1`, `start + 1`) instead of Python-side integer math. The
bodies with no such arithmetic (unsigned DISPLAY, COMP-3, BINARY, and
their BigInteger equivalents) needed no second copy at all - they
already just interpolate `start`/`end` wherever they appear, so
passing the literal int or the string "start"/"end" produces correct
Java either way.

An OCCURS leaf gains an `int index` parameter and a bounds check
(`IllegalArgumentException`, not a sentinel return - Java's unchecked
exceptions mean there's no Go-style zero-value-plus-error to thread
back, simplifying this relative to Go's own OCCURS slice). An OCCURS
group gains the same bounds check and constructs the child with a
freshly computed `newBase` - still one small heap allocation per
call, as every nested-group accessor already was. Indexing is
0-based, matching `generate_java()`'s own `[N]Type` array convention,
same as Go's.

Eighth slice: REDEFINES dispatch, mirroring go_decoder.py's own eighth
slice's RedefinesRule/RedefinesDispatch shape exactly (imported
directly from go_decoder.py, not duplicated - the shape is entirely
language-agnostic: a discriminator name, and value->variant rules).
Where Go's own mechanism is "interface+type-switch" (no sealed-
interface language feature to reach for), Java actually has one -
ADR 0009's own context names a *sealed interface* for Java
specifically - so this slice uses it for real: `public sealed
interface {Target}Overlay permits A, B {}`, with every named view's
class declared `public static final class A implements {Target}Overlay`.
Sealed interfaces are a Java 17+ feature; decision 0006 deliberately
keeps the plain POJO generator at no JDK floor above 8/11, but asked
rather than assumed whether the decoder path should inherit that same
constraint for this one slice - resolved in favor of letting the
decoder have its own, higher floor, since it is already a distinct
artifact from the POJO generator and ADR 0009 names the sealed
interface literally, not as a suggestion to work around.

The dispatcher method decodes the sibling discriminator into a local
`var` and compares it with a plain if/else chain, not a `switch` -
deliberately, even for a numeric discriminator: Java's classic switch
statement doesn't accept `long` as a selector type at all (unlike
Go's own switch, which has no such restriction), and the discriminator
could resolve to any of byte/short/int/long/String depending on its
own PIC - an if/else chain stays correct for all five without a
width-specific special case. A numeric rule value is normalized to a
canonical decimal literal first (`str(int(value))`), for the exact
Go's-own reason: avoiding Java's legacy leading-zero-means-octal
literal syntax. Dispatch target/sibling/discriminator classes share
the target's own `base` context unchanged (REDEFINES overlays the
same bytes; it never reslices or shifts position), so their
constructor call is `new Variant(buf)` or `new Variant(buf, this.base)`
depending on whether the enclosing scope already has a `base` field -
the identical rule plain nested-group accessors already follow.

Ninth slice: BigDecimal construction for decimal/scaled fields - the
one item go_decoder.py's own eight slices never needed (decision
0002's Go policy is a scaled int64 with the scale tracked only as a
comment, not a real part of the Go type), because decision 0002 itself
already says Java has no equivalent gap: java_rules.py's decimal
ladder resolves every scale > 0 field to BigDecimal unconditionally,
regardless of usage or whether the unscaled magnitude would fit a
native long - so unlike the fifth slice's BigInteger (which BINARY
never reaches, since every BINARY tier's own digit ceiling already
fits its native signed type), a *decimal* BINARY field does reach this
slice. The unscaled magnitude is decoded with exactly the fifth
slice's own machinery - decodeDisplayDigitsBig/decodePackedDecimalBig
for DISPLAY/COMP-3, a plain native read (short/int/long, masked and
widened the same way the second slice's unsigned BINARY path already
is) for COMP/COMP-4/COMP-5/BINARY - then wrapped with `new
java.math.BigDecimal(unscaled, scale)`, where `scale` is the DSL's own
FieldNode.scale (fractional-digit count), a codegen-time literal
baked straight into the generated source, never computed at runtime.
Unlike Go's int64, where the scale has to live in a side comment
because int64 itself carries no scale, BigDecimal tracks its own scale
natively - so this slice needs no documentation-only comment the way
decision 0002's own consequences section describes for Go.

New dedicated body generators (`_unsigned_display_body_bigdecimal` and
its signed/leading/separate-sign/packed/binary siblings, each with an
"_occurs" twin where offset arithmetic is involved, mirroring the
fifth and seventh slices' own pattern exactly) parallel the existing
BigInteger-returning ones body-for-body, differing only in their final
return expression(s) (`return new java.math.BigDecimal(v, scale);`
instead of `return v;`) - written as separate functions rather than
retrofitting the existing, already round-trip-verified BigInteger
functions with an optional scale parameter, so this slice touches zero
previously-tested code paths.
"""

import json

from unbolt.datatypes.sizing import (
    is_alpha_pic,
    is_binary_usage,
    is_edited_pic,
    is_national_pic,
    is_packed_usage,
)
from unbolt.dsl.schema import Dsl, FieldNode
from unbolt.exceptions import UnsupportedDecodeError
from unbolt.generators.go_decoder import RedefinesDispatch, RedefinesRule
from unbolt.generators.naming import go_field_name, java_field_name

__all__ = ["RedefinesDispatch", "RedefinesRule", "generate_java_decoder"]

_INTEGER_JAVA_TYPES = frozenset({"byte", "short", "int", "long"})
_BIG_INTEGER_JAVA_TYPE = "BigInteger"
_BIG_DECIMAL_JAVA_TYPE = "BigDecimal"
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

_CP037_CHARSET_FIELD = (
    'private static final java.nio.charset.Charset CP037 = '
    'java.nio.charset.Charset.forName("Cp037");'
)

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


def generate_java_decoder(
    dsl: Dsl, resolved: dict[str, str], *, redefines: dict[str, RedefinesDispatch] | None = None
) -> dict[str, str]:
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
        redefines (dict[str, RedefinesDispatch] | None): REDEFINES
            target field name -> how to pick its active overlaid view
            at decode time (see module docstring and go_decoder.py's
            own RedefinesDispatch, reused directly here). A REDEFINES
            field with no entry for its target here still raises,
            exactly as before this parameter existed.
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
    redefines_by_target = redefines or {}
    for root in dsl.roots:
        if root.pic is not None or not root.children:
            raise UnsupportedDecodeError(
                f"java decoder: root {root.name!r} must be a group in this slice"
            )
        needs: set[str] = set()
        body = _render_class(
            root, root.name, resolved, needs, top_level=True, base=None,
            redefines=redefines_by_target,
        )
        helpers = []
        if "alpha" in needs:
            helpers.append(_CP037_CHARSET_FIELD)
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
    base: int | None,
    redefines: dict[str, RedefinesDispatch],
    implements_clause: str | None = None,
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

    base: what absolute offset this class's own buf[0] corresponds to
        - None everywhere this class is reachable without ever
          passing through an OCCURS group (no base field at all, the
          original bare-absolute-offset scheme, unchanged); otherwise
          the group's own node.offset once an OCCURS ancestor has been
          entered - see the module docstring's OCCURS section.
    redefines: see generate_java_decoder's own parameter. A direct
        child whose own name is a key here is a REDEFINES dispatch
        target; its overlay siblings (children whose `.redefines`
        names that same target) are rendered as part of its dispatch
        block, not independently.
    implements_clause: the sealed interface this class implements, for
        a REDEFINES dispatch view only - None for every other class
        (root, plain nested group, or OCCURS element).
    """
    class_name = go_field_name(node.name)
    keyword = "public class" if top_level else "public static class"
    if implements_clause is not None:
        keyword = "public static final class"
    has_base_field = base is not None

    dispatch_targets = {child.name: child for child in node.children if child.name in redefines}
    absorbed = {
        child.name
        for child in node.children
        if child.redefines is not None and child.redefines in dispatch_targets
    }

    accessor_blocks: list[str] = []
    nested_bodies: list[str] = []
    for child in node.children:
        if child.name in absorbed:
            continue
        if child.name in dispatch_targets:
            siblings = [c for c in node.children if c.redefines == child.name]
            accessor_blocks.append(
                _render_redefines_dispatch(
                    child, siblings, node.children, field_path, resolved, needs,
                    nested_bodies, base, redefines[child.name], redefines,
                )
            )
            continue
        if child.redefines is not None:
            raise UnsupportedDecodeError(
                f"java decoder: REDEFINES field {child.name!r} isn't supported yet"
            )
        child_path = f"{field_path}.{child.name}"
        if child.pic is None and child.children:
            child_class_name = go_field_name(child.name)
            child_base = child.offset if child.occurs is not None else base
            nested_bodies.append(
                _render_class(
                    child, child_path, resolved, needs, top_level=False, base=child_base,
                    redefines=redefines,
                )
            )
            method_name, _ = java_field_name(child.name, source_line=child.source_line)
            getter_name = f"get{method_name[0].upper()}{method_name[1:]}"
            if child.occurs is not None:
                accessor_blocks.append(
                    _render_occurs_group_accessor(getter_name, child, base, child_class_name)
                )
            else:
                ctor_args = "buf, this.base" if base is not None else "buf"
                accessor_blocks.append(
                    f"public {child_class_name} {getter_name}() {{\n"
                    f"    return new {child_class_name}({ctor_args});\n"
                    "}"
                )
            continue
        accessor_blocks.append(_render_leaf_accessor(child, child_path, resolved, needs, base))

    class_decl = f"{keyword} {class_name}"
    if implements_clause is not None:
        class_decl += f" implements {implements_clause}"
    lines = [f"{class_decl} {{", "    private final java.nio.ByteBuffer buf;"]
    if has_base_field:
        lines.append("    private final int base;")
    lines.append("")
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
    elif has_base_field:
        lines += [
            f"    {class_name}(java.nio.ByteBuffer buf, int base) {{",
            "        this.buf = buf;",
            "        this.base = base;",
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


def _render_occurs_group_accessor(
    getter_name: str, node: FieldNode, base: int | None, child_class_name: str
) -> str:
    rel_start = node.offset - (base if base is not None else 0)
    base_term = "this.base + " if base is not None else ""
    rel_term = "" if rel_start == 0 else f"{rel_start} + "
    return (
        f"public {child_class_name} {getter_name}(int index) {{\n"
        f"    if (index < 0 || index >= {node.occurs}) {{\n"
        f'        throw new IllegalArgumentException("{node.name}: index " + index + '
        f'" out of range [0, {node.occurs})");\n'
        "    }\n"
        f"    int newBase = {base_term}{rel_term}index * {node.byte_size};\n"
        f"    return new {child_class_name}(buf, newBase);\n"
        "}"
    )


def _render_redefines_dispatch(
    target: FieldNode,
    overlay_siblings: list[FieldNode],
    parent_children: tuple[FieldNode, ...],
    field_path: str,
    resolved: dict[str, str],
    needs: set[str],
    nested_bodies: list[str],
    base: int | None,
    dispatch: RedefinesDispatch,
    redefines: dict[str, RedefinesDispatch],
) -> str:
    """Emits every overlaid view's class (implementing a sealed
    interface), the interface itself, and one dispatcher method
    (named after `target`) that decodes `dispatch`'s discriminator and
    picks the active view - see the module docstring's REDEFINES
    section for the scope this enforces (mirrors go_decoder.py's own
    _render_redefines_dispatch almost exactly; Java's version uses a
    sealed interface instead of a marker method, and an if/else chain
    instead of a switch, for reasons explained there).
    """
    variants = [target, *overlay_siblings]
    for variant in variants:
        if variant.pic is not None or not variant.children:
            raise UnsupportedDecodeError(
                f"java decoder: REDEFINES dispatch on {variant.name!r} requires a group - "
                "a leaf-level overlay isn't supported yet"
            )
        if variant.occurs is not None:
            raise UnsupportedDecodeError(
                f"java decoder: REDEFINES dispatch combined with OCCURS on {variant.name!r} "
                "isn't supported yet"
            )

    variant_by_name = {variant.name: variant for variant in variants}
    for rule in dispatch.rules:
        if rule.variant not in variant_by_name:
            raise UnsupportedDecodeError(
                f"java decoder: REDEFINES dispatch for {target.name!r}: rule variant "
                f"{rule.variant!r} is neither the target nor one of its REDEFINES siblings"
            )

    discriminator = next((c for c in parent_children if c.name == dispatch.discriminator), None)
    if discriminator is None:
        raise UnsupportedDecodeError(
            f"java decoder: REDEFINES dispatch for {target.name!r}: discriminator "
            f"{dispatch.discriminator!r} isn't a sibling field"
        )
    if discriminator.pic is None or discriminator.occurs is not None:
        raise UnsupportedDecodeError(
            f"java decoder: REDEFINES dispatch for {target.name!r}: discriminator "
            f"{dispatch.discriminator!r} must be a single elementary, non-OCCURS field"
        )
    if is_edited_pic(discriminator.pic) or is_national_pic(discriminator.pic):
        raise UnsupportedDecodeError(
            f"java decoder: REDEFINES dispatch for {target.name!r}: edited/national "
            f"discriminator {dispatch.discriminator!r} isn't supported"
        )

    target_class_name = go_field_name(target.name)
    interface_name = f"{target_class_name}Overlay"
    target_method_name, _ = java_field_name(target.name, source_line=target.source_line)
    getter_name = f"get{target_method_name[0].upper()}{target_method_name[1:]}"

    variant_class_names: dict[str, str] = {}
    for variant in variants:
        variant_class_name = go_field_name(variant.name)
        variant_class_names[variant.name] = variant_class_name
        nested_bodies.append(
            _render_class(
                variant, f"{field_path}.{variant.name}", resolved, needs, top_level=False,
                base=base, redefines=redefines, implements_clause=interface_name,
            )
        )
    nested_bodies.append(
        f"public sealed interface {interface_name} permits "
        + ", ".join(variant_class_names[v.name] for v in variants)
        + " {}"
    )

    discriminator_is_alpha = is_alpha_pic(discriminator.pic)
    discriminator_method_name, _ = java_field_name(
        discriminator.name, source_line=discriminator.source_line
    )
    discriminator_getter = (
        f"get{discriminator_method_name[0].upper()}{discriminator_method_name[1:]}"
    )
    ctor_args = "buf, this.base" if base is not None else "buf"

    lines = [
        f"public {interface_name} {getter_name}() {{",
        f"    var discriminator = {discriminator_getter}();",
    ]
    for rule in dispatch.rules:
        literal = _redefines_rule_literal(rule.value, discriminator_is_alpha, target.name)
        variant_class_name = variant_class_names[rule.variant]
        cond = (
            f"discriminator.equals({literal})"
            if discriminator_is_alpha
            else f"discriminator == {literal}"
        )
        lines.append(f"    if ({cond}) {{")
        lines.append(f"        return new {variant_class_name}({ctor_args});")
        lines.append("    }")
    lines.append(
        f'    throw new IllegalArgumentException("{getter_name}: discriminator " + discriminator + '
        '" matches no configured variant");'
    )
    lines.append("}")
    return "\n".join(lines)


def _redefines_rule_literal(value: str, is_alpha: bool, target_name: str) -> str:
    if is_alpha:
        return json.dumps(value)
    try:
        return str(int(value))
    except ValueError:
        raise UnsupportedDecodeError(
            f"java decoder: REDEFINES dispatch for {target_name!r}: rule value {value!r} "
            "isn't a valid integer for its numeric discriminator"
        ) from None


def _runtime_position_preamble(
    field_label: str, base: int | None, occurs: int | None, rel_start: int, byte_size: int
) -> str:
    """Declares local `start`/`end` variables an occurs-mode body reads
    from, instead of the literal ints a non-runtime body bakes in
    directly - see the module docstring's OCCURS section.
    """
    lines: list[str] = []
    base_term = "this.base + " if base is not None else ""
    if occurs is not None:
        lines.append(f"    if (index < 0 || index >= {occurs}) {{")
        lines.append(
            f'        throw new IllegalArgumentException("{field_label}: index " + index + '
            f'" out of range [0, {occurs})");'
        )
        lines.append("    }")
        rel_term = "" if rel_start == 0 else f"{rel_start} + "
        start_expr = f"{base_term}{rel_term}index * {byte_size}"
    else:
        # runtime with occurs is None only happens because base is not
        # None (that's the only other way the caller's `runtime` check
        # becomes true), so this.base is always valid here.
        start_expr = f"this.base + {rel_start}" if rel_start != 0 else "this.base"
    lines.append(f"    int start = {start_expr};")
    lines.append(f"    int end = start + {byte_size};")
    return "\n".join(lines) + "\n"


def _render_leaf_accessor(
    node: FieldNode,
    field_path: str,
    resolved: dict[str, str],
    needs: set[str],
    base: int | None,
) -> str:
    if node.pic is None:
        raise UnsupportedDecodeError(
            f"java decoder: COMP-1/COMP-2 field {node.name!r} isn't supported yet"
        )
    if node.redefines is not None:
        raise UnsupportedDecodeError(
            f"java decoder: REDEFINES field {node.name!r} isn't supported yet"
        )
    if is_edited_pic(node.pic) or is_national_pic(node.pic):
        raise UnsupportedDecodeError(
            f"java decoder: edited/national field {node.name!r} isn't supported yet"
        )

    method_name, _ = java_field_name(node.name, source_line=node.source_line)
    getter_name = f"get{method_name[0].upper()}{method_name[1:]}"
    occurs = node.occurs
    runtime = base is not None or occurs is not None
    rel_start = node.offset - (base if base is not None else 0)

    if is_alpha_pic(node.pic):
        # Alphanumeric fields never go through mapping's integer
        # ladder (mapping/engine.py excludes them from candidate
        # generation), so field_path has no entry in resolved -
        # checking is_alpha_pic first, before ever touching
        # resolved[field_path], is what avoids a KeyError here.
        needs.add("alpha")
        if runtime:
            return _render_alpha_accessor_occurs(
                getter_name, base, occurs, rel_start, node.byte_size
            )
        start, end = node.offset, node.offset + node.byte_size
        return _render_alpha_accessor(getter_name, start, end)

    java_type = resolved[field_path]
    if (
        java_type not in (_BIG_INTEGER_JAVA_TYPE, _BIG_DECIMAL_JAVA_TYPE)
        and java_type not in _INTEGER_JAVA_TYPES
    ):
        raise UnsupportedDecodeError(
            f"java decoder: resolved type {java_type!r} for {field_path!r} isn't supported "
            "in this slice (only byte/short/int/long/BigInteger/BigDecimal)"
        )

    if java_type == _BIG_DECIMAL_JAVA_TYPE:
        return _render_bigdecimal_leaf_accessor(
            node, getter_name, base, occurs, rel_start, needs, node.scale
        )

    if java_type == _BIG_INTEGER_JAVA_TYPE:
        return _render_bigint_leaf_accessor(node, getter_name, base, occurs, rel_start, needs)

    params = "int index" if occurs is not None else ""
    if runtime:
        preamble = _runtime_position_preamble(node.name, base, occurs, rel_start, node.byte_size)
        if is_packed_usage(node.usage):
            needs.add("packed")
            body = _packed_body("start", "end", node.digits, java_type)
        elif is_binary_usage(node.usage):
            body = _binary_body("start", node.byte_size, node.signed, java_type)
        elif node.usage.upper() == "DISPLAY":
            if not node.signed:
                body = _unsigned_display_body(node.name, "start", "end", java_type)
            elif node.sign_separate:
                body = _separate_sign_display_body_occurs(
                    node.name, node.sign_leading, java_type
                )
            elif node.sign_leading:
                body = _leading_overpunch_display_body_occurs(node.name, java_type)
            else:
                body = _signed_display_body_occurs(node.name, java_type)
        else:
            raise UnsupportedDecodeError(
                f"java decoder: only DISPLAY/COMP-3/binary fields are supported in this "
                f"slice, got {node.usage!r} for {node.name!r}"
            )
        return f"public {java_type} {getter_name}({params}) {{\n" + preamble + body + "}"

    start, end = node.offset, node.offset + node.byte_size
    if is_packed_usage(node.usage):
        needs.add("packed")
        body = _packed_body(start, end, node.digits, java_type)
    elif is_binary_usage(node.usage):
        body = _binary_body(start, node.byte_size, node.signed, java_type)
    elif node.usage.upper() == "DISPLAY":
        if not node.signed:
            body = _unsigned_display_body(node.name, start, end, java_type)
        elif node.sign_separate:
            body = _separate_sign_display_body(node.name, start, end, node.sign_leading, java_type)
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


def _render_alpha_accessor(getter_name: str, start: int, end: int) -> str:
    byte_size = end - start
    index_expr = "i" if start == 0 else f"i - {start}"
    return (
        f"public String {getter_name}() {{\n"
        f"    byte[] bytes = new byte[{byte_size}];\n"
        f"    for (int i = {start}; i < {end}; i++) {{\n"
        f"        bytes[{index_expr}] = buf.get(i);\n"
        "    }\n"
        "    return new String(bytes, CP037);\n"
        "}"
    )


def _render_alpha_accessor_occurs(
    getter_name: str, base: int | None, occurs: int | None, rel_start: int, byte_size: int
) -> str:
    preamble = _runtime_position_preamble(getter_name, base, occurs, rel_start, byte_size)
    params = "int index" if occurs is not None else ""
    return (
        f"public String {getter_name}({params}) {{\n"
        + preamble
        + f"    byte[] bytes = new byte[{byte_size}];\n"
        "    for (int i = start; i < end; i++) {\n"
        "        bytes[i - start] = buf.get(i);\n"
        "    }\n"
        "    return new String(bytes, CP037);\n"
        "}"
    )


def _render_bigint_leaf_accessor(
    node: FieldNode,
    getter_name: str,
    base: int | None,
    occurs: int | None,
    rel_start: int,
    needs: set[str],
) -> str:
    runtime = base is not None or occurs is not None
    params = "int index" if occurs is not None else ""

    if runtime:
        preamble = _runtime_position_preamble(node.name, base, occurs, rel_start, node.byte_size)
        if is_packed_usage(node.usage):
            needs.add("bigint_packed")
            body = _packed_body_big("start", "end", node.digits)
        elif node.usage.upper() == "DISPLAY":
            needs.add("bigint_display")
            if not node.signed:
                body = _unsigned_display_body_big("start", "end")
            elif node.sign_separate:
                body = _separate_sign_display_body_big_occurs(node.name, node.sign_leading)
            elif node.sign_leading:
                body = _leading_overpunch_display_body_big_occurs(node.name)
            else:
                body = _signed_display_body_big_occurs(node.name)
        else:
            raise UnsupportedDecodeError(
                f"java decoder: BigInteger is only supported for DISPLAY/COMP-3 fields in "
                f"this slice, got {node.usage!r} for {node.name!r}"
            )
        return f"public java.math.BigInteger {getter_name}({params}) {{\n" + preamble + body + "}"

    start, end = node.offset, node.offset + node.byte_size
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


def _render_bigdecimal_leaf_accessor(
    node: FieldNode,
    getter_name: str,
    base: int | None,
    occurs: int | None,
    rel_start: int,
    needs: set[str],
    scale: int,
) -> str:
    # Every decimal (scale > 0) field resolves to BigDecimal regardless
    # of usage or magnitude (java_rules.py's own decimal ladder has only
    # one valid candidate) - unlike the BigInteger accessor above, which
    # BINARY never reaches (every BINARY tier's own digit ceiling always
    # fits its native signed type, so a *plain* integer field never
    # needs BigInteger). A *decimal* BINARY field still needs BigDecimal
    # for its scale, even though its unscaled magnitude fits a native
    # long - so BINARY is in scope here, read via the exact same
    # _binary_body machinery the integer ladder already uses, then
    # widened into a BigInteger before the final BigDecimal wrap.
    runtime = base is not None or occurs is not None
    params = "int index" if occurs is not None else ""

    if runtime:
        preamble = _runtime_position_preamble(node.name, base, occurs, rel_start, node.byte_size)
        if is_packed_usage(node.usage):
            needs.add("bigint_packed")
            body = _packed_body_bigdecimal("start", "end", node.digits, scale)
        elif is_binary_usage(node.usage):
            body = _binary_body_bigdecimal("start", node.byte_size, node.signed, scale)
        elif node.usage.upper() == "DISPLAY":
            needs.add("bigint_display")
            if not node.signed:
                body = _unsigned_display_body_bigdecimal("start", "end", scale)
            elif node.sign_separate:
                body = _separate_sign_display_body_bigdecimal_occurs(
                    node.name, node.sign_leading, scale
                )
            elif node.sign_leading:
                body = _leading_overpunch_display_body_bigdecimal_occurs(node.name, scale)
            else:
                body = _signed_display_body_bigdecimal_occurs(node.name, scale)
        else:
            raise UnsupportedDecodeError(
                f"java decoder: only DISPLAY/COMP-3/binary fields are supported in this "
                f"slice, got {node.usage!r} for {node.name!r}"
            )
        return (
            f"public java.math.BigDecimal {getter_name}({params}) {{\n" + preamble + body + "}"
        )

    start, end = node.offset, node.offset + node.byte_size
    if is_packed_usage(node.usage):
        needs.add("bigint_packed")
        body = _packed_body_bigdecimal(start, end, node.digits, scale)
    elif is_binary_usage(node.usage):
        body = _binary_body_bigdecimal(start, node.byte_size, node.signed, scale)
    elif node.usage.upper() == "DISPLAY":
        needs.add("bigint_display")
        if not node.signed:
            body = _unsigned_display_body_bigdecimal(start, end, scale)
        elif node.sign_separate:
            body = _separate_sign_display_body_bigdecimal(
                node.name, start, end, node.sign_leading, scale
            )
        elif node.sign_leading:
            body = _leading_overpunch_display_body_bigdecimal(node.name, start, end, scale)
        else:
            body = _signed_display_body_bigdecimal(node.name, start, end, scale)
    else:
        raise UnsupportedDecodeError(
            f"java decoder: only DISPLAY/COMP-3/binary fields are supported in this "
            f"slice, got {node.usage!r} for {node.name!r}"
        )
    return f"public java.math.BigDecimal {getter_name}() {{\n" + body + "}"


def _unsigned_display_body_bigdecimal(start: int | str, end: int | str, scale: int) -> str:
    return (
        f"    java.math.BigInteger v = decodeDisplayDigitsBig(buf, {start}, {end});\n"
        f"    return new java.math.BigDecimal(v, {scale});\n"
    )


def _signed_display_body_bigdecimal(field_label: str, start: int, end: int, scale: int) -> str:
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
        f"    return new java.math.BigDecimal(v, {scale});\n"
    )


def _leading_overpunch_display_body_bigdecimal(
    field_label: str, start: int, end: int, scale: int
) -> str:
    return (
        f"    int first = buf.get({start}) & 0xFF;\n"
        "    int zone = first & 0xF0;\n"
        "    int digit = first & 0x0F;\n"
        "    if (digit > 9) {\n"
        f'        throw new IllegalArgumentException("{field_label}: first byte " + '
        'String.format("0x%02X", first) + " has a non-digit value nibble " + digit);\n'
        "    }\n"
        f"    java.math.BigInteger tail = decodeDisplayDigitsBig(buf, {start + 1}, {end});\n"
        f"    java.math.BigInteger tenPow = java.math.BigInteger.TEN.pow({end - start - 1});\n"
        "    java.math.BigInteger v = java.math.BigInteger.valueOf(digit).multiply(tenPow)"
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
        f"    return new java.math.BigDecimal(v, {scale});\n"
    )


def _separate_sign_display_body_bigdecimal(
    field_label: str, start: int, end: int, sign_leading: bool, scale: int
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
        f"            return new java.math.BigDecimal(v, {scale});\n"
        "        case 0x60:\n"
        f"            return new java.math.BigDecimal(v.negate(), {scale});\n"
        "        default:\n"
        f'            throw new IllegalArgumentException("{field_label}: separate sign byte " + '
        'String.format("0x%02X", sign) + " is not \'+\' or \'-\'");\n'
        "    }\n"
    )


def _signed_display_body_bigdecimal_occurs(field_label: str, scale: int) -> str:
    return (
        "    java.math.BigInteger v = decodeDisplayDigitsBig(buf, start, end - 1);\n"
        "    int last = buf.get(end - 1) & 0xFF;\n"
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
        f"    return new java.math.BigDecimal(v, {scale});\n"
    )


def _leading_overpunch_display_body_bigdecimal_occurs(field_label: str, scale: int) -> str:
    return (
        "    int first = buf.get(start) & 0xFF;\n"
        "    int zone = first & 0xF0;\n"
        "    int digit = first & 0x0F;\n"
        "    if (digit > 9) {\n"
        f'        throw new IllegalArgumentException("{field_label}: first byte " + '
        'String.format("0x%02X", first) + " has a non-digit value nibble " + digit);\n'
        "    }\n"
        "    java.math.BigInteger tail = decodeDisplayDigitsBig(buf, start + 1, end);\n"
        "    java.math.BigInteger tenPow = java.math.BigInteger.TEN.pow(end - start - 1);\n"
        "    java.math.BigInteger v = java.math.BigInteger.valueOf(digit).multiply(tenPow)"
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
        f"    return new java.math.BigDecimal(v, {scale});\n"
    )


def _separate_sign_display_body_bigdecimal_occurs(
    field_label: str, sign_leading: bool, scale: int
) -> str:
    if sign_leading:
        sign_expr, digits_start, digits_end = "start", "start + 1", "end"
    else:
        sign_expr, digits_start, digits_end = "end - 1", "start", "end - 1"
    return (
        f"    int sign = buf.get({sign_expr}) & 0xFF;\n"
        f"    java.math.BigInteger v = decodeDisplayDigitsBig(buf, {digits_start}, "
        f"{digits_end});\n"
        "    switch (sign) {\n"
        "        case 0x4E:\n"
        f"            return new java.math.BigDecimal(v, {scale});\n"
        "        case 0x60:\n"
        f"            return new java.math.BigDecimal(v.negate(), {scale});\n"
        "        default:\n"
        f'            throw new IllegalArgumentException("{field_label}: separate sign byte " + '
        'String.format("0x%02X", sign) + " is not \'+\' or \'-\'");\n'
        "    }\n"
    )


def _packed_body_bigdecimal(start: int | str, end: int | str, digits: int, scale: int) -> str:
    return (
        f"    java.math.BigInteger v = decodePackedDecimalBig(buf, {start}, {end}, {digits});\n"
        f"    return new java.math.BigDecimal(v, {scale});\n"
    )


def _binary_body_bigdecimal(start: int | str, byte_size: int, signed: bool, scale: int) -> str:
    reader = _BINARY_WIDTH_READER[byte_size]
    native_type = _BINARY_NATIVE_TYPE[byte_size]
    mask = None if signed else _UNSIGNED_WIDEN_MASK.get(byte_size)
    if mask is None:
        return (
            f"    {native_type} raw = buf.{reader}({start});\n"
            "    java.math.BigInteger v = java.math.BigInteger.valueOf(raw);\n"
            f"    return new java.math.BigDecimal(v, {scale});\n"
        )
    return (
        f"    {native_type} raw = buf.{reader}({start});\n"
        f"    java.math.BigInteger v = java.math.BigInteger.valueOf(raw & {mask});\n"
        f"    return new java.math.BigDecimal(v, {scale});\n"
    )


def _unsigned_display_body_big(start: int | str, end: int | str) -> str:
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


def _signed_display_body_big_occurs(field_label: str) -> str:
    return (
        "    java.math.BigInteger v = decodeDisplayDigitsBig(buf, start, end - 1);\n"
        "    int last = buf.get(end - 1) & 0xFF;\n"
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


def _leading_overpunch_display_body_big_occurs(field_label: str) -> str:
    return (
        "    int first = buf.get(start) & 0xFF;\n"
        "    int zone = first & 0xF0;\n"
        "    int digit = first & 0x0F;\n"
        "    if (digit > 9) {\n"
        f'        throw new IllegalArgumentException("{field_label}: first byte " + '
        'String.format("0x%02X", first) + " has a non-digit value nibble " + digit);\n'
        "    }\n"
        "    java.math.BigInteger tail = decodeDisplayDigitsBig(buf, start + 1, end);\n"
        "    java.math.BigInteger scale = java.math.BigInteger.TEN.pow(end - start - 1);\n"
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


def _separate_sign_display_body_big_occurs(field_label: str, sign_leading: bool) -> str:
    if sign_leading:
        sign_expr, digits_start, digits_end = "start", "start + 1", "end"
    else:
        sign_expr, digits_start, digits_end = "end - 1", "start", "end - 1"
    return (
        f"    int sign = buf.get({sign_expr}) & 0xFF;\n"
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


def _packed_body_big(start: int | str, end: int | str, digits: int) -> str:
    return f"    return decodePackedDecimalBig(buf, {start}, {end}, {digits});\n"


def _unsigned_display_body(
    field_label: str, start: int | str, end: int | str, java_type: str
) -> str:
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


def _signed_display_body_occurs(field_label: str, java_type: str) -> str:
    return (
        "    long v = 0;\n"
        "    for (int i = start; i < end - 1; i++) {\n"
        "        int b = buf.get(i) & 0xFF;\n"
        "        if (b < 0xF0 || b > 0xF9) {\n"
        f'            throw new IllegalArgumentException("{field_label}: byte " + '
        'String.format("0x%02X", b) + " is not a DISPLAY digit");\n'
        "        }\n"
        "        v = v * 10 + (b & 0x0F);\n"
        "    }\n"
        "    int last = buf.get(end - 1) & 0xFF;\n"
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


def _leading_overpunch_display_body_occurs(field_label: str, java_type: str) -> str:
    return (
        "    int first = buf.get(start) & 0xFF;\n"
        "    int zone = first & 0xF0;\n"
        "    int digit = first & 0x0F;\n"
        "    if (digit > 9) {\n"
        f'        throw new IllegalArgumentException("{field_label}: first byte " + '
        'String.format("0x%02X", first) + " has a non-digit value nibble " + digit);\n'
        "    }\n"
        "    long v = digit;\n"
        "    for (int i = start + 1; i < end; i++) {\n"
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


def _separate_sign_display_body_occurs(field_label: str, sign_leading: bool, java_type: str) -> str:
    if sign_leading:
        sign_expr, digits_start, digits_end = "start", "start + 1", "end"
    else:
        sign_expr, digits_start, digits_end = "end - 1", "start", "end - 1"
    return (
        f"    int sign = buf.get({sign_expr}) & 0xFF;\n"
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


def _packed_body(start: int | str, end: int | str, digits: int, java_type: str) -> str:
    return (
        f"    long v = decodePackedDecimal(buf, {start}, {end}, {digits});\n"
        f"    return ({java_type}) v;\n"
    )


def _binary_body(start: int | str, byte_size: int, signed: bool, java_type: str) -> str:
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

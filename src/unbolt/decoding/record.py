"""Decode one record's real bytes into real field values, using the
FieldNode.offset/byte_size that build_dsl() already computes (ADR 0008).
Elementary DISPLAY, COMP-3/PACKED-DECIMAL, and COMP/COMP-4/COMP-5/
BINARY fields are supported; groups are walked transparently; anything
else (COMP-1/COMP-2, alphanumeric/edited/national, OCCURS) raises
rather than guessing at a decode this slice doesn't implement yet
(phase.md Phase 8).
"""

from unbolt.datatypes.sizing import (
    is_alpha_pic,
    is_binary_usage,
    is_edited_pic,
    is_national_pic,
    is_packed_usage,
)
from unbolt.decoding.codecs import DEFAULT_CODEPAGE, decode_binary, decode_display, decode_packed
from unbolt.dsl.schema import FieldNode
from unbolt.exceptions import RecordLengthMismatchError, UnsupportedDecodeError


def decode_record(
    root: FieldNode, data: bytes, *, codepage: str = DEFAULT_CODEPAGE
) -> dict[str, object]:
    """Decode one record's bytes into {field_path: value}.

    Args: root (FieldNode): a Dsl root (01/77-level item) to decode against.
        data (bytes): the record's raw bytes; length must equal
            root.byte_size exactly.
        codepage (str): EBCDIC code page; cp037 by default (decision 0010).
    Returns: dict[str, object]: dot-joined field_path -> decoded value,
        one entry per elementary DISPLAY/COMP-3/binary field under root
        (groups aren't included, matching mapping/validation's own
        convention).
    Raises:
        RecordLengthMismatchError: len(data) != root.byte_size - rejected
            by default (decision 0010), no best-effort decode in this slice.
        UnsupportedDecodeError: a field under root isn't a plain DISPLAY,
            COMP-3/PACKED-DECIMAL, or COMP/COMP-4/COMP-5/BINARY
            elementary item (COMP-1/COMP-2, alphanumeric/edited/
            national, and OCCURS decode are later Phase 8 slices).
    """
    if len(data) != root.byte_size:
        raise RecordLengthMismatchError(
            f"{root.name!r}: expected {root.byte_size} bytes, got {len(data)}"
        )
    values: dict[str, object] = {}
    _decode_node(root, root.name, data, codepage, values)
    return values


def _decode_node(
    node: FieldNode, path: str, data: bytes, codepage: str, values: dict[str, object]
) -> None:
    if node.occurs is not None:
        raise UnsupportedDecodeError(f"{path!r}: OCCURS decode isn't supported yet")
    if node.pic is None and node.children:
        for child in node.children:
            _decode_node(child, f"{path}.{child.name}", data, codepage, values)
        return
    if node.pic is None:
        raise UnsupportedDecodeError(f"{path!r}: COMP-1/COMP-2 decode isn't supported yet")
    if is_alpha_pic(node.pic) or is_edited_pic(node.pic) or is_national_pic(node.pic):
        raise UnsupportedDecodeError(
            f"{path!r}: alphanumeric/edited/national field decode isn't supported yet"
        )
    raw = data[node.offset : node.offset + node.byte_size]
    if is_packed_usage(node.usage):
        values[path] = decode_packed(raw, digits=node.digits, scale=node.scale)
        return
    if is_binary_usage(node.usage):
        values[path] = decode_binary(raw, signed=node.signed, scale=node.scale)
        return
    if node.usage.upper() != "DISPLAY":
        raise UnsupportedDecodeError(
            f"{path!r}: only DISPLAY/COMP-3/binary decode is supported in this "
            f"slice, got {node.usage}"
        )
    values[path] = decode_display(
        raw,
        signed=node.signed,
        sign_separate=node.sign_separate,
        sign_leading=node.sign_leading,
        scale=node.scale,
        codepage=codepage,
    )

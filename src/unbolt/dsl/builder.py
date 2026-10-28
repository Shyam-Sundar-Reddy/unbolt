"""AST -> DSL: attach digits/scale/byte_size to every field, bottom-up,
then offset to every field, top-down (a field's offset depends on its
position among its siblings, which byte_size alone doesn't determine).
"""

import dataclasses

from unbolt.datatypes.sizing import (
    alpha_byte_size,
    edited_pic_width,
    is_alpha_pic,
    is_edited_pic,
    is_national_pic,
    is_signed,
    national_pic_width,
    numeric_byte_size,
    parse_pic_digits_scale,
)
from unbolt.dsl.schema import Dsl, FieldNode
from unbolt.parser.ast import AstNode
from unbolt.parser.parser import ParseResult


def build_dsl(parse_result: ParseResult, *, source_file: str, version: str = "2") -> Dsl:
    roots = tuple(_assign_offsets(_build_field(node), 0) for node in parse_result.roots)
    return Dsl(version=version, source_file=source_file, roots=roots)


def _build_field(node: AstNode) -> FieldNode:
    children = tuple(_build_field(child) for child in node.children)

    if node.pic is None and children:
        digits, scale, signed = 0, 0, False
        byte_size = _group_byte_size(children)
    elif node.pic is None:
        # Elementary item with no PIC: only valid for COMP-1/COMP-2, whose
        # byte size doesn't depend on digits (there are none to count).
        digits, scale, signed = 0, 0, False
        byte_size = numeric_byte_size(node.usage, digits, node.sign_separate)
    elif is_edited_pic(node.pic):
        # Display-formatting symbols (Z, *, $, comma, ...) - counted as
        # text width, never as digits (CBL-W050 already diagnosed this
        # at parse time).
        digits, scale, signed = 0, 0, False
        byte_size = edited_pic_width(node.pic)
    elif is_national_pic(node.pic):
        # National/DBCS (CBL-W060 already diagnosed this at parse time) -
        # double-byte text width, never digits; no DBCS codec exists.
        digits, scale, signed = 0, 0, False
        byte_size = national_pic_width(node.pic)
    elif is_alpha_pic(node.pic):
        digits, scale, signed = 0, 0, False
        byte_size = alpha_byte_size(node.pic)
    else:
        signed = is_signed(node.pic)
        digits, scale = parse_pic_digits_scale(node.pic)
        byte_size = numeric_byte_size(node.usage, digits, node.sign_separate)

    return FieldNode(
        name=node.name,
        level=node.level,
        pic=node.pic,
        usage=node.usage,
        signed=signed,
        sign_separate=node.sign_separate,
        sign_leading=node.sign_leading,
        digits=digits,
        scale=scale,
        byte_size=byte_size,
        occurs=node.occurs,
        redefines=node.redefines,
        value=None,
        source_line=node.source_line,
        offset=0,  # placeholder - _assign_offsets fills in the real value
        children=children,
    )


def _assign_offsets(node: FieldNode, base_offset: int) -> FieldNode:
    """Top-down pass: every field's byte offset within its parent.

    A non-REDEFINES child starts right after the previous one, advancing
    by its own byte_size * occurs. A REDEFINES child shares the offset
    of the field it redefines - and, if it's wider, pushes the cursor
    forward so the *next* sibling doesn't overlap it, mirroring
    _group_byte_size's "the overlay's footprint grows to fit it" exactly.
    """
    children: list[FieldNode] = []
    cursor = base_offset
    offset_by_name: dict[str, int] = {}
    extent_by_name: dict[str, int] = {}

    for child in node.children:
        size = child.byte_size * (child.occurs or 1)
        if child.redefines is None:
            child_offset = cursor
            offset_by_name[child.name] = child_offset
            extent_by_name[child.name] = child_offset + size
            cursor += size
        else:
            child_offset = offset_by_name.get(child.redefines, cursor)
            end = child_offset + size
            prior_extent = extent_by_name.get(child.redefines, child_offset)
            if end > prior_extent:
                cursor += end - prior_extent
                extent_by_name[child.redefines] = end
        children.append(_assign_offsets(child, child_offset))

    return dataclasses.replace(node, offset=base_offset, children=tuple(children))


def _group_byte_size(children: tuple[FieldNode, ...]) -> int:
    """Sum of children's sizes, each repeated by its own OCCURS count.

    A REDEFINES child doesn't add new bytes - it shares its target's
    offset - unless it's larger, in which case the overlay's footprint
    grows to fit it (goal.md: REDEFINES is a union of the overlaid items).
    """
    contributions: dict[str, int] = {}
    total = 0
    for child in children:
        if child.redefines is None:
            size = child.byte_size * (child.occurs or 1)
            contributions[child.name] = size
            total += size
    for child in children:
        if child.redefines is not None:
            size = child.byte_size * (child.occurs or 1)
            original = contributions.get(child.redefines, 0)
            if size > original:
                total += size - original
    return total

"""Entry splitting, clause parsing, and level-number tree building.

Scope (see docs/supported-constructs.md): levels 01-49 and 77; PIC; USAGE
(DISPLAY default, COMP/COMP-1..5/BINARY/PACKED-DECIMAL and their
COMPUTATIONAL synonyms); OCCURS n [TIMES]; REDEFINES name; SIGN [IS]
LEADING|TRAILING [SEPARATE]. Level 66, OCCURS ... DEPENDING ON, and
COPY ... REPLACING are recognized only enough to produce a diagnostic.
VALUE literals are recognized as a clause boundary and skipped (not
extracted) - no Phase 1 fixture depends on their content.
"""

from unbolt.datatypes.sizing import is_edited_pic, is_national_pic
from unbolt.exceptions import InputTooLargeError, InvalidInputError
from unbolt.parser import diagnostics as diag
from unbolt.parser.ast import AstNode
from unbolt.parser.diagnostics import Diagnostic
from unbolt.parser.tokenizer import Token, tokenize

MAX_SOURCE_BYTES = 2_000_000

_BARE_USAGE_KEYWORDS = {
    "DISPLAY",
    "COMP",
    "COMP-1",
    "COMP-2",
    "COMP-3",
    "COMP-4",
    "COMP-5",
    "BINARY",
    "PACKED-DECIMAL",
    "COMPUTATIONAL",
    "COMPUTATIONAL-1",
    "COMPUTATIONAL-2",
    "COMPUTATIONAL-3",
    "COMPUTATIONAL-4",
    "COMPUTATIONAL-5",
}
_USAGE_SYNONYMS = {
    "COMPUTATIONAL": "COMP",
    "COMPUTATIONAL-1": "COMP-1",
    "COMPUTATIONAL-2": "COMP-2",
    "COMPUTATIONAL-3": "COMP-3",
    "COMPUTATIONAL-4": "COMP-4",
    "COMPUTATIONAL-5": "COMP-5",
}
_SUPPORTED_DIALECTS = {"ibm-enterprise"}
_SUPPORTED_CHARSETS = {"ebcdic", "ascii"}


class ParseResult:
    __slots__ = ("roots", "diagnostics")

    def __init__(self, roots: tuple[AstNode, ...], diagnostics: tuple[Diagnostic, ...]) -> None:
        self.roots = roots
        self.diagnostics = diagnostics


def parse_copybook(
    source: str,
    *,
    dialect: str = "ibm-enterprise",
    charset: str = "ebcdic",
) -> ParseResult:
    """Parse supported COBOL data declarations from a copybook.

    Args:
        source: copybook text.
        dialect: only "ibm-enterprise" is implemented.
        charset: "ebcdic" or "ascii". Currently a provenance-only setting -
            Phase 1 parses declarations, not real data bytes, so charset
            has no effect yet. It will matter once a record decoder
            (goal.md Extended scope) actually reads EBCDIC/ASCII bytes.
    Returns:
        ParseResult: the field tree plus every diagnostic raised along the
        way. Unsupported syntax becomes a diagnostic, never an exception.
    Raises:
        InvalidInputError: empty source, or an unsupported dialect/charset.
        InputTooLargeError: source exceeds MAX_SOURCE_BYTES.
    """
    if dialect not in _SUPPORTED_DIALECTS:
        raise InvalidInputError(
            f"unsupported dialect {dialect!r}; only 'ibm-enterprise' is implemented"
        )
    if charset not in _SUPPORTED_CHARSETS:
        raise InvalidInputError(f"unsupported charset {charset!r}; expected 'ebcdic' or 'ascii'")
    if len(source.encode("utf-8", errors="replace")) > MAX_SOURCE_BYTES:
        raise InputTooLargeError(f"source exceeds {MAX_SOURCE_BYTES} bytes")
    if not source.strip():
        raise InvalidInputError("source is empty")

    tokens = tokenize(source)
    entries = _split_entries(tokens)

    diagnostics: list[Diagnostic] = []
    nodes: list[AstNode] = []
    for entry in entries:
        node = _parse_entry(entry, diagnostics)
        if node is not None:
            nodes.append(node)

    roots = _build_tree(nodes, diagnostics)
    return ParseResult(roots=tuple(roots), diagnostics=tuple(diagnostics))


def _split_entries(tokens: list[Token]) -> list[list[Token]]:
    entries: list[list[Token]] = []
    current: list[Token] = []
    for token in tokens:
        if token.text == ".":
            if current:
                entries.append(current)
                current = []
            continue
        current.append(token)
    if current:
        entries.append(current)
    return entries


def _parse_entry(entry: list[Token], diagnostics: list[Diagnostic]) -> AstNode | None:
    first = entry[0]
    if first.text.upper() == "COPY":
        diagnostics.append(diag.copy_replacing_unsupported(first.line))
        return None

    try:
        level = int(first.text)
    except ValueError:
        detail = f"expected a level number, got {first.text!r}"
        diagnostics.append(diag.malformed_entry(first.line, detail))
        return None

    if level == 66:
        diagnostics.append(diag.renames_unsupported(first.line))
        return None

    if len(entry) < 2:
        detail = "missing a name after the level number"
        diagnostics.append(diag.malformed_entry(first.line, detail))
        return None

    name = entry[1].text
    node = AstNode(
        name=name,
        level=level,
        pic=None,
        usage="DISPLAY",
        occurs=None,
        redefines=None,
        sign_separate=False,
        sign_leading=False,
        source_line=first.line,
    )
    _parse_clauses(entry[2:], node, diagnostics)
    return node


def _parse_clauses(tokens: list[Token], node: AstNode, diagnostics: list[Diagnostic]) -> None:
    i = 0
    n = len(tokens)
    while i < n:
        word = tokens[i].text
        upper = word.upper()

        if upper in ("PIC", "PICTURE"):
            i += 1
            if i < n and tokens[i].text.upper() == "IS":
                i += 1
            if i < n:
                node.pic = tokens[i].text
                if is_edited_pic(node.pic):
                    diagnostics.append(diag.edited_picture_detected(tokens[i].line, node.pic))
                elif is_national_pic(node.pic):
                    diagnostics.append(diag.national_picture_detected(tokens[i].line, node.pic))
                i += 1
            continue

        if upper == "USAGE":
            i += 1
            if i < n and tokens[i].text.upper() == "IS":
                i += 1
            if i < n:
                node.usage = _USAGE_SYNONYMS.get(tokens[i].text.upper(), tokens[i].text.upper())
                i += 1
            continue

        if upper in _BARE_USAGE_KEYWORDS:
            node.usage = _USAGE_SYNONYMS.get(upper, upper)
            i += 1
            continue

        if upper == "OCCURS":
            i += 1
            count = None
            if i < n and tokens[i].text.isdigit():
                count = int(tokens[i].text)
                i += 1
            depends = False
            while i < n and tokens[i].text.upper() not in (
                "PIC", "PICTURE", "USAGE", "REDEFINES", "SIGN", "VALUE",
                "SYNCHRONIZED", "SYNC", "JUSTIFIED", "JUST", "BLANK",
            ) and tokens[i].text.upper() not in _BARE_USAGE_KEYWORDS:
                if tokens[i].text.upper() == "DEPENDING":
                    depends = True
                i += 1
            if depends:
                diagnostics.append(diag.occurs_depending_on_unsupported(tokens[0].line))
                node.occurs = None
            else:
                node.occurs = count
            continue

        if upper == "REDEFINES":
            i += 1
            if i < n:
                node.redefines = tokens[i].text
                i += 1
            continue

        if upper == "SIGN":
            i += 1
            if i < n and tokens[i].text.upper() == "IS":
                i += 1
            if i < n and tokens[i].text.upper() in ("LEADING", "TRAILING"):
                node.sign_leading = tokens[i].text.upper() == "LEADING"
                i += 1
            if i < n and tokens[i].text.upper() == "SEPARATE":
                node.sign_separate = True
                i += 1
                if i < n and tokens[i].text.upper() == "CHARACTER":
                    i += 1
            continue

        if upper == "VALUE":
            i += 1
            if i < n and tokens[i].text.upper() == "IS":
                i += 1
            if i < n:
                i += 1  # the literal; content is not extracted in Phase 1
            continue

        if upper in ("SYNCHRONIZED", "SYNC"):
            diagnostics.append(diag.synchronized_not_modeled(tokens[i].line))
            i += 1
            if i < n and tokens[i].text.upper() in ("LEFT", "RIGHT"):
                i += 1
            continue

        if upper in ("JUSTIFIED", "JUST"):
            diagnostics.append(diag.justified_not_modeled(tokens[i].line))
            i += 1
            if i < n and tokens[i].text.upper() == "RIGHT":
                i += 1
            continue

        if upper == "BLANK":
            diagnostics.append(diag.blank_when_zero_not_modeled(tokens[i].line))
            i += 1
            if i < n and tokens[i].text.upper() == "WHEN":
                i += 1
            if i < n and tokens[i].text.upper() == "ZERO":
                i += 1
            continue

        diagnostics.append(diag.unrecognized_clause(tokens[i].line, word))
        i += 1


def _build_tree(nodes: list[AstNode], diagnostics: list[Diagnostic]) -> list[AstNode]:
    roots: list[AstNode] = []
    stack: list[AstNode] = []
    for node in nodes:
        if node.level == 77:
            roots.append(node)
            stack.clear()
            continue
        while stack and stack[-1].level >= node.level:
            stack.pop()
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)
    return roots

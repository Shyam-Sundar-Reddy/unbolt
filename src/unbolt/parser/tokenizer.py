"""Turn copybook source text into a flat stream of (word, line) tokens.

Comments and layout are discarded here; grammar (what a PIC clause looks
like, where one entry ends) is the parser's job, not the tokenizer's.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Token:
    text: str
    line: int


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    for line_no, raw_line in enumerate(source.splitlines(), start=1):
        if _is_comment(raw_line):
            continue
        for word in raw_line.split():
            if word == ".":
                tokens.append(Token(".", line_no))
            elif word.endswith("."):
                tokens.append(Token(word[:-1], line_no))
                tokens.append(Token(".", line_no))
            else:
                tokens.append(Token(word, line_no))
    return tokens


def _is_comment(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("*>"):
        return True
    # Traditional fixed-format comment indicator: '*' in column 7.
    return len(line) > 6 and line[6] == "*"

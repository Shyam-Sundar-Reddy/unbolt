"""COBOL identifier -> Go/Java identifier (goal.md §8 Q6, decision 0003).

ACCOUNT-AGE -> AccountAge (Go, exported) / accountAge (Java). Go's
capitalized convention structurally dodges every Go keyword (they're
always lowercase); Java's camelCase doesn't, so a Java reserved-word
collision gets a deterministic '_' suffix plus an info diagnostic -
traceable, not silent, but no per-field decision needed for a fully
mechanical case.
"""

from unbolt.parser.diagnostics import Diagnostic, java_reserved_word_renamed

# https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.9
_JAVA_RESERVED = frozenset(
    {
        "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char",
        "class", "const", "continue", "default", "do", "double", "else", "enum",
        "extends", "final", "finally", "float", "for", "goto", "if", "implements",
        "import", "instanceof", "int", "interface", "long", "native", "new",
        "package", "private", "protected", "public", "return", "short", "static",
        "strictfp", "super", "switch", "synchronized", "this", "throw", "throws",
        "transient", "try", "void", "volatile", "while",
        "true", "false", "null", "var", "record", "yield", "sealed", "permits",
    }
)


def _words(cobol_name: str) -> list[str]:
    return [w for w in cobol_name.split("-") if w]


def go_field_name(cobol_name: str) -> str:
    return "".join(word.capitalize() for word in _words(cobol_name))


def java_field_name(cobol_name: str, *, source_line: int) -> tuple[str, tuple[Diagnostic, ...]]:
    words = _words(cobol_name)
    if not words:
        return "", ()
    name = words[0].lower() + "".join(word.capitalize() for word in words[1:])
    if name in _JAVA_RESERVED:
        renamed = f"{name}_"
        return renamed, (java_reserved_word_renamed(source_line, name, renamed),)
    return name, ()

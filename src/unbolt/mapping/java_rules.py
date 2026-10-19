from unbolt.datatypes import TypeFacts
from unbolt.mapping.integer_ladder import TypeSpec, evaluate_integer_ladder
from unbolt.mapping.model import Candidate

# goal.md §5.7. No unsigned entries here on purpose: Java has no unsigned
# primitives, so an unsigned COBOL field is checked against these same
# signed ranges and naturally lands on a wider type than its Go
# counterpart would need - see docs/mapping-rules.md for a worked example.
JAVA_INTEGER_LADDER: tuple[TypeSpec, ...] = (
    TypeSpec("byte", -128, 127),
    TypeSpec("short", -32768, 32767),
    TypeSpec("int", -2147483648, 2147483647),
    TypeSpec("long", -(2**63), 2**63 - 1),
    TypeSpec("BigInteger", -(10**40 - 1), 10**40 - 1),
)


def java_integer_candidates(facts: TypeFacts) -> tuple[Candidate, ...]:
    return evaluate_integer_ladder(facts, JAVA_INTEGER_LADDER, "java-int")


def java_decimal_candidates(facts: TypeFacts) -> tuple[Candidate, ...]:
    """BigDecimal always; float/double always rejected (hard rule)."""
    del facts  # every decimal field gets the same three candidates
    return (
        Candidate(
            "float",
            "invalid",
            "java-decimal-float",
            "float cannot represent a decimal field exactly; rejected by default (hard rule)",
        ),
        Candidate(
            "double",
            "invalid",
            "java-decimal-double",
            "double cannot represent a decimal field exactly; rejected by default (hard rule)",
        ),
        Candidate(
            "BigDecimal",
            "valid",
            "java-decimal-bigdecimal",
            "BigDecimal holds any precision and scale exactly",
        ),
    )

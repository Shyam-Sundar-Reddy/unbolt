from decimal import Decimal

from unbolt.datatypes import TypeFacts
from unbolt.mapping.integer_ladder import TypeSpec, evaluate_integer_ladder
from unbolt.mapping.model import Candidate

_INT64_MIN = Decimal(-(2**63))
_INT64_MAX = Decimal(2**63 - 1)

# goal.md §5.7. big.Int's bounds are a practically-infinite stand-in -
# arbitrary precision has no real max, but a concrete number lets it
# share the same range-fit check as every other rung.
GO_INTEGER_LADDER: tuple[TypeSpec, ...] = (
    TypeSpec("int8", -128, 127),
    TypeSpec("int16", -32768, 32767),
    TypeSpec("int32", -2147483648, 2147483647),
    TypeSpec("int64", -(2**63), 2**63 - 1),
    TypeSpec("uint8", 0, 255),
    TypeSpec("uint16", 0, 65535),
    TypeSpec("uint32", 0, 2**32 - 1),
    TypeSpec("uint64", 0, 2**64 - 1),
    TypeSpec("big.Int", -(10**40 - 1), 10**40 - 1),
)


def go_integer_candidates(facts: TypeFacts) -> tuple[Candidate, ...]:
    return evaluate_integer_ladder(facts, GO_INTEGER_LADDER, "go-int")


def go_decimal_candidates(facts: TypeFacts) -> tuple[Candidate, ...]:
    """decision 0002: scaled int64, falling back to a string on overflow."""
    candidates = [
        Candidate(
            "float32",
            "invalid",
            "go-decimal-float32",
            "float32 cannot represent a decimal field exactly; rejected by default (hard rule)",
        ),
        Candidate(
            "float64",
            "invalid",
            "go-decimal-float64",
            "float64 cannot represent a decimal field exactly; rejected by default (hard rule)",
        ),
    ]
    scale_factor = Decimal(10) ** facts.scale
    unscaled_min = facts.min_value * scale_factor
    unscaled_max = facts.max_value * scale_factor
    if unscaled_min >= _INT64_MIN and unscaled_max <= _INT64_MAX:
        candidates.append(
            Candidate(
                "int64 (scaled)",
                "valid",
                "go-decimal-int64-scaled",
                f"unscaled value fits int64 ({unscaled_min}..{unscaled_max}); "
                f"caller divides by 10^{facts.scale} (decision 0002)",
            )
        )
    else:
        candidates.append(
            Candidate(
                "int64 (scaled)",
                "invalid",
                "go-decimal-int64-scaled",
                f"unscaled value {unscaled_min}..{unscaled_max} exceeds int64's range",
            )
        )
        candidates.append(
            Candidate(
                "string",
                "valid",
                "go-decimal-string-fallback",
                "unscaled value exceeds int64; falls back to an exact string (decision 0002)",
            )
        )
    return tuple(candidates)

"""Regenerate docs/mapping-rules.md from the actual rule objects.

Run after changing GO_INTEGER_LADDER, JAVA_INTEGER_LADDER, or either
decimal rule function - don't hand-edit the generated file.
"""

# ruff: noqa: E501 - long lines below are markdown table rows, not code.

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from unbolt.mapping.engine import RULE_SET_VERSION  # noqa: E402
from unbolt.mapping.go_rules import GO_INTEGER_LADDER  # noqa: E402
from unbolt.mapping.java_rules import JAVA_INTEGER_LADDER  # noqa: E402


def _ladder_table(ladder: tuple, rule_prefix: str) -> str:
    lines = ["| Rule id | Type | Min | Max |", "|---|---|---|---|"]
    for spec in ladder:
        lines.append(f"| `{rule_prefix}-{spec.name}` | `{spec.name}` | {spec.min_value} | {spec.max_value} |")
    return "\n".join(lines)


def main() -> None:
    content = f"""# Mapping rules (rule-set version `{RULE_SET_VERSION}`)

Generated from `src/unbolt/mapping/*.py` by `tools/gen_mapping_rules_doc.py` -
regenerate, don't hand-edit. Every rule's outcome is a fact about whether
a type's range covers a field's range; see `recommend_mappings()` for how
these are dispatched (integer ladder if `scale == 0`, decimal rule
otherwise - the dispatch looks at scale, not USAGE).

## Go integer ladder

Checked in this order; every entry is reported, not just the first fit.
`big.Int`'s bounds are a practically-infinite stand-in for arbitrary
precision.

{_ladder_table(GO_INTEGER_LADDER, "go-int")}

## Java integer ladder

No unsigned entries - Java has none. An unsigned COBOL field is checked
against these same signed ranges, which is why it can need a wider type
than its Go counterpart (see `docs/decisions/0001...md` test:
`test_java_has_no_unsigned_so_needs_a_bigger_type_than_go`).

{_ladder_table(JAVA_INTEGER_LADDER, "java-int")}

## Go decimal rules (decision 0002)

| Rule id | Type | Outcome | Condition |
|---|---|---|---|
| `go-decimal-float32` | `float32` | always invalid | hard rule: never float for decimal/packed fields |
| `go-decimal-float64` | `float64` | always invalid | hard rule: never float for decimal/packed fields |
| `go-decimal-int64-scaled` | `int64` (scaled) | valid if the unscaled value fits `int64` | `-2^63 <= unscaled <= 2^63-1` |
| `go-decimal-string-fallback` | `string` | valid when `int64` overflows | unscaled value exceeds `int64`'s range |

## Java decimal rules

| Rule id | Type | Outcome | Condition |
|---|---|---|---|
| `java-decimal-float` | `float` | always invalid | hard rule: never float for decimal/packed fields |
| `java-decimal-double` | `double` | always invalid | hard rule: never float for decimal/packed fields |
| `java-decimal-bigdecimal` | `BigDecimal` | always valid | arbitrary precision and scale |
"""
    out_path = ROOT / "docs" / "mapping-rules.md"
    out_path.write_text(content)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()

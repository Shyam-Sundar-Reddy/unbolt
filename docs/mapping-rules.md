# Mapping rules (rule-set version `0`)

Generated from `src/unbolt/mapping/*.py` by `tools/gen_mapping_rules_doc.py` -
regenerate, don't hand-edit. Every rule's outcome is a fact about whether
a type's range covers a field's range; see `recommend_mappings()` for how
these are dispatched (integer ladder if `scale == 0`, decimal rule
otherwise - the dispatch looks at scale, not USAGE).

## Go integer ladder

Checked in this order; every entry is reported, not just the first fit.
`big.Int`'s bounds are a practically-infinite stand-in for arbitrary
precision.

| Rule id | Type | Min | Max |
|---|---|---|---|
| `go-int-int8` | `int8` | -128 | 127 |
| `go-int-int16` | `int16` | -32768 | 32767 |
| `go-int-int32` | `int32` | -2147483648 | 2147483647 |
| `go-int-int64` | `int64` | -9223372036854775808 | 9223372036854775807 |
| `go-int-uint8` | `uint8` | 0 | 255 |
| `go-int-uint16` | `uint16` | 0 | 65535 |
| `go-int-uint32` | `uint32` | 0 | 4294967295 |
| `go-int-uint64` | `uint64` | 0 | 18446744073709551615 |
| `go-int-big.Int` | `big.Int` | -9999999999999999999999999999999999999999 | 9999999999999999999999999999999999999999 |

## Java integer ladder

No unsigned entries - Java has none. An unsigned COBOL field is checked
against these same signed ranges, which is why it can need a wider type
than its Go counterpart (see `docs/decisions/0001...md` test:
`test_java_has_no_unsigned_so_needs_a_bigger_type_than_go`).

| Rule id | Type | Min | Max |
|---|---|---|---|
| `java-int-byte` | `byte` | -128 | 127 |
| `java-int-short` | `short` | -32768 | 32767 |
| `java-int-int` | `int` | -2147483648 | 2147483647 |
| `java-int-long` | `long` | -9223372036854775808 | 9223372036854775807 |
| `java-int-BigInteger` | `BigInteger` | -9999999999999999999999999999999999999999 | 9999999999999999999999999999999999999999 |

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

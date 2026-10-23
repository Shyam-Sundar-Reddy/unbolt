# Supported constructs

Status matrix for Phase 1's parser. Dialect: IBM Enterprise COBOL only.
Default charset: EBCDIC. Default `TRUNC`: `STD` (decision 0001, an
internal ADR not pushed with this repo).

Legend: **Supported** (parsed, typed, generated) · **Partial** (parsed and
typed, not generated/mapped yet) · **Diagnostic** (recognized, reported,
never silently converted) · **Unsupported** (not recognized in Phase 1).

## Structure

| Construct | Status | Notes |
|---|---|---|
| Level `01`–`49` | Supported | hierarchy: groups (have children) vs elementary items (have a PIC) |
| Level `77` | Supported | standalone item, no parent record |
| Level `88` | Partial | recognized as a non-storage node and excluded from mapping (no false type assigned); the `VALUE` literal itself isn't extracted (`FieldNode.value` is always `None`) |
| Level `66` (`RENAMES`) | Diagnostic | recognized, reported as unsupported |
| `OCCURS n` | Supported | fixed repetition |
| `OCCURS … DEPENDING ON` | Diagnostic | variable-length table, detected and reported |
| `REDEFINES` | Supported | parsed as overlay metadata; mapping policy is still open (§8 Q7, Phase 2) |
| `SYNCHRONIZED` | Diagnostic | detected, affects offsets, not modeled in Phase 1 |
| `JUSTIFIED`, `BLANK WHEN ZERO` | Partial | preserved as metadata, no behavioral effect yet |
| Edited pictures (`Z`, `*`, `$`, `,`, `.`, `+`, `-`, `CR`, `DB`) | Diagnostic | display-formatting only; treated as text |
| `COPY … REPLACING` | Diagnostic | text substitution; reported if unresolved |
| `VALUE` | Partial | preserved as metadata |

## Data types (USAGE)

| USAGE | Status | Notes |
|---|---|---|
| `DISPLAY` (default, zoned decimal) | Supported | one byte per digit; EBCDIC overpunch sign decoding |
| `COMP-3` / `PACKED-DECIMAL` | Supported | two digits per byte, sign in the last nibble |
| `COMP` / `COMP-4` / `BINARY` | Supported | halfword/fullword/doubleword by digit count, `TRUNC(STD)`-limited range |
| `COMP-5` | Supported | same byte-size tiers as `COMP`/`COMP-4`, but range uses the full native binary capacity (not PIC-digit-limited) regardless of `TRUNC` — see decision 0001 |
| `COMP-1` / `COMP-2` | Partial | parsed and sized (4/8 bytes); flagged "needs explicit policy" since IBM uses hexadecimal floating point, not IEEE 754 |
| `PIC X(n)` / `PIC A(n)` | Supported | alphanumeric / alphabetic |
| `PIC N(n)` / `PIC G(n)` (national/DBCS) | Unsupported | not recognized in Phase 1 |
| `SIGN IS SEPARATE` | Supported | adds one byte vs. overpunched sign |

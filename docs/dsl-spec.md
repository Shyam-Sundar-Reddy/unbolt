# DSL v1 spec

Defined in `src/unbolt/dsl/schema.py`. Two frozen, slotted dataclasses —
immutable: once built, a DSL tree never changes. Mapping decisions and
overrides (Phase 2) live in separate objects, never mutate these.

**v0 → v1 (Phase 8, ADR 0008)**: added `FieldNode.offset`. `Dsl.from_json()`
hard-fails (`SchemaVersionError`) on a v0 JSON file — there's no
migration path, since `offset` has no meaningful default to backfill
with; re-parse the original copybook with the current version instead.

## `FieldNode`

One COBOL data item — either a **group** (has `children`, no `pic`) or an
**elementary item** (has a `pic`, no `children`).

| Field | Type | Meaning |
|---|---|---|
| `name` | `str` | Raw COBOL identifier, e.g. `ACCOUNT-BALANCE` |
| `level` | `int` | `01`–`49`, `66`, `77`, or `88` |
| `pic` | `str \| None` | Raw PIC string (`"S9(7)V99"`), or `None` for a group or a `COMP-1`/`COMP-2` field (they take no PIC) |
| `usage` | `str` | `"DISPLAY"`, `"COMP"`, `"COMP-1"`, `"COMP-2"`, `"COMP-3"`, `"COMP-4"`, `"COMP-5"` |
| `signed` | `bool` | Whether the PIC has `S` |
| `sign_separate` | `bool` | `SIGN IS SEPARATE` present (adds one byte vs. overpunched) |
| `digits` | `int` | Total digit count, integer + fractional (`S9(7)V99` → 9) |
| `scale` | `int` | Fractional digit count — the `V` position (`S9(7)V99` → 2) |
| `byte_size` | `int` | Computed storage size; see docs/acceptance-criteria.md for the formulas per USAGE |
| `occurs` | `int \| None` | Fixed repetition count (`OCCURS n`); `None` if not a table |
| `redefines` | `str \| None` | Name of the field this one overlays, or `None` |
| `value` | `str \| None` | Raw `VALUE` clause text, or the literal for a level-88 condition name |
| `source_line` | `int` | Line number in the original copybook — the traceability anchor |
| `offset` | `int` | Byte offset within its immediate parent (0 for a top-level root). An `OCCURS` field's offset is where its *first* occurrence starts — occurrence `i` starts at `offset + i * byte_size`, computed by a decoder, not stored per-occurrence. A `REDEFINES` field shares its target's offset; if it's wider, later siblings' offsets account for the wider extent, not the original's (ADR 0008, Phase 8) |
| `children` | `tuple[FieldNode, ...]` | Nested items, in source order; empty for elementary items |

## `Dsl`

| Field | Type | Meaning |
|---|---|---|
| `version` | `str` | DSL schema version — bump this, not the field shapes, when the schema changes |
| `source_file` | `str` | Path/name of the copybook this was built from |
| `roots` | `tuple[FieldNode, ...]` | Top-level `01`/`77` items, in source order |

## What's deliberately NOT here yet

- No `(de)serialization` methods (`to_json`/`from_json`) — Phase 1.
- No computed `min`/`max` range or candidate target types — that's
  `TypeFacts` (Phase 1, `datatypes/`) and `MappingReport` (Phase 2), kept
  as separate objects so the DSL stays pure source fact, never a decision.
- No diagnostics list — Phase 1's `ParseResult` carries those alongside a
  `Dsl`, not inside it.

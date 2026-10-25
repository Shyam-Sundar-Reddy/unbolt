# Limitations

Written by actually running the behavior described, not from memory of
what should work — three claims in `docs/supported-constructs.md` turned
out to be false once exercised (COMP-5, level 88, edited pictures, all
fixed; see `CHANGELOG.md`). Treat this list the same way: verify before
trusting, don't just re-read the code.

## Dialect and real data

- **One dialect, no real byte decoding.** Only IBM Enterprise COBOL's
  documented rules are modeled (decision 0001). `charset`
  (`ebcdic`/`ascii`) is accepted as a parameter on `parse_copybook()`
  but is currently a **no-op** — the parser reads copybook *source
  text* (always plain text), never actual mainframe *data records*.
  There is no EBCDIC overpunch-sign decoder yet. You get a correct
  schema and correct byte-size math; you cannot yet point this tool at
  a real fixed-width data file and get decoded values out. That's the
  "record decoder," tracked as Extended scope (goal.md §7).
- **`TRUNC(STD)` only.** `TRUNC(BIN)`/`TRUNC(OPT)` aren't modeled.
  `COMP-5` is the one documented exception (always full binary range,
  per decision 0001) — everything else assumes the safe, PIC-limited
  default.

## Constructs that are diagnosed, not converted

These produce a diagnostic (`docs/diagnostics.md`) and the entry is
dropped — never silently misconverted:

- Level 66 (`RENAMES`)
- `OCCURS ... DEPENDING ON` (variable-length tables)
- `COPY ... REPLACING`

## Constructs that parse correctly but aren't fully modeled

- **Level 88** (condition names): correctly excluded from numeric
  mapping (no false type assigned), but the `VALUE` literal itself
  isn't extracted — `FieldNode.value` is always `None`.
- **`JUSTIFIED`**: detected (info diagnostic `CBL-I101`) but not stored
  anywhere — no `FieldNode` field carries it.
- **`BLANK WHEN ZERO`**: detected (info diagnostic `CBL-I103`) but not
  stored anywhere, same as `JUSTIFIED` — no behavioral effect, no
  `FieldNode` field carries it.
- **PIC `N`/`G`** (national/DBCS): recognized (`CBL-W060`), sized as
  double-byte text width, excluded from numeric mapping and generation
  (fixed in `0.1.1` — it previously fell through to the numeric path
  and silently sized as `digits=0`). Not decoded: there's no DBCS
  character codec, so the field's byte width is correct but its content
  is never interpreted.
- **Any other PIC symbol** outside `9 S V X A N G` plus the recognized
  edited-picture characters: **still not validated**. A field using one
  won't raise an error and won't be caught by `is_alpha_pic`/
  `is_edited_pic`/`is_national_pic`/the numeric path cleanly — it risks
  silently producing a wrong digit count or byte size, the same bug
  shape fixed for `COMP-1`/`COMP-2`, level 88, edited pictures, and
  national pictures. Known, not yet fixed. If you hit this, the symptom
  is a suspiciously small `byte_size` or `digits` for a field that
  visually has neither.

## Mapping and code generation

- **Go and Java only.** Rust/TypeScript/Avro/Protobuf/etc. are Extended
  scope (goal.md §7) — not implemented, not partially implemented.
- **`REDEFINES` codegen is struct-shape only** (decision 0005): the
  original and redefining items become two independent fields with a
  comment, not a real memory overlay. True union/overlay semantics are
  deferred until a record decoder exists to actually need them.
- **Go's decimal scale isn't self-describing.** A scaled `int64` field
  (decision 0002) requires the caller to know and apply the scale
  manually — nothing generated computes `value / 10^scale` for you.
- **Sibling-name collisions** aren't handled: two different COBOL
  fields that happen to produce the same generated identifier (e.g.
  `ACCOUNT-ID` and `ACCOUNT_ID` both → `AccountId`) will silently
  collide. Explicitly out of scope per decision 0003, not yet raised
  as its own question.

## Performance

- No CI regression budget yet (`docs/performance.md` explains why: the
  first real measurement needs a second run to compare against, which
  doesn't exist yet).
- Benchmarks only go up to 10,000 synthetic fields; 100,000 hasn't been
  tried.

## Interfaces

- MCP tools take a `file_path`, not inline source — each call re-reads
  from disk. Fine for local use (stdio transport, copybooks never
  leave the machine); not designed for a remote/sandboxed MCP host.
- An overrides file (decision 0007) is implicitly scoped to one
  `--target` — using different type choices for Go vs. Java on the
  same copybook needs two separate `--overrides-file` paths.

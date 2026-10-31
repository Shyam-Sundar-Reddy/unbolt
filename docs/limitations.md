# Limitations

Written by actually running the behavior described, not from memory of
what should work — three claims in `docs/supported-constructs.md` turned
out to be false once exercised (COMP-5, level 88, edited pictures, all
fixed; see `CHANGELOG.md`). Treat this list the same way: verify before
trusting, don't just re-read the code.

## Dialect and real data

- **One dialect.** Only IBM Enterprise COBOL's documented rules are
  modeled (decision 0001). `charset` (`ebcdic`/`ascii`) is accepted as a
  parameter on `parse_copybook()` but is currently a **no-op** — the
  parser reads copybook *source text* (always plain text), never actual
  mainframe *data records*. Real byte decoding is a separate module
  (`unbolt.decoding`, Phase 8) with its own, narrower scope (next item).
- **Record decoding (`unbolt.decoding`, Phase 8) covers DISPLAY, COMP-3,
  and binary so far.** `decode_record()` decodes plain `DISPLAY` (zoned
  decimal) fields — unsigned, and signed via EBCDIC overpunch or `SIGN
  IS SEPARATE` (`cp037` default, decision 0010), either leading or
  trailing (`FieldNode.sign_leading`, DSL v2); `COMP-3`/`PACKED-DECIMAL`
  fields (two digits per byte, sign in the last nibble); and `COMP`/
  `COMP-4`/`COMP-5`/`BINARY` fields (big-endian two's-complement/
  unsigned integers) — all including through nested groups and
  `REDEFINES`'s shared offsets. It does **not yet** decode: `COMP-1`/
  `COMP-2` (float — no safe default, goal.md §5.4), alphanumeric/edited/
  national fields, or `OCCURS` tables — each raises
  `UnsupportedDecodeError` rather than guessing. A fixed-length record
  whose byte length doesn't match its layout is rejected outright
  (`RecordLengthMismatchError`), never best-effort decoded (decision
  0010). `decode_rdw_record()` parses and validates a 4-byte RDW
  (Record Descriptor Word) variable-length-record header — big-endian
  total length including the header itself, reserved bytes must be
  zero (spanned records aren't supported) — then hands the extracted
  payload to `decode_record()` unchanged: the payload still has to
  match `root.byte_size` exactly, decision 0010's rule isn't relaxed
  for variable-length records. There's no support yet for reading a
  *stream* of multiple RDW records back to back (one call decodes one
  record) or for the spanned-record segment-descriptor convention.
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

## Compatibility classification (`unbolt.variants`, Phase 9)

- **Structural, not a decode guarantee.** `classify_compatibility()`
  (decision 0011) judges two DSL shapes, not whether `decode_record()`
  will actually tolerate the length difference today — it still
  requires an exact length match (decision 0010), with no best-effort
  decode for a `FORWARD`/`BACKWARD` trailing change.
- **No rename detection.** A field renamed but otherwise identical is
  classified as one `removed` + one `added`, not recognized as the
  same field continuing under a new name. No alias mechanism exists to
  say otherwise.
- **`REDEFINES` overlays aren't compared.** Changing which field a
  `REDEFINES` targets, or adding/removing an overlay, isn't reflected
  in the classifier's signature fields unless it also happens to shift
  an offset or byte size — a `redefines` value changing in place,
  silently, is a known gap for this first slice.
- No CLI command or YAML variant/discriminator config yet — only the
  pure `classify_compatibility(old_root, new_root)` function exists so
  far; `unbolt check` and multi-root/multi-variant copybooks are a
  later Phase 9 slice.

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

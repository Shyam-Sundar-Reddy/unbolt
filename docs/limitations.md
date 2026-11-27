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
- **Record decoding (`unbolt.decoding`, Phase 8) covers DISPLAY,
  COMP-3, binary, and plain alphanumeric so far.** `decode_record()`
  decodes plain `DISPLAY` (zoned decimal) fields — unsigned, and
  signed via EBCDIC overpunch or `SIGN IS SEPARATE` (`cp037` default,
  decision 0010), either leading or trailing (`FieldNode.sign_leading`,
  DSL v2); `COMP-3`/`PACKED-DECIMAL` fields (two digits per byte, sign
  in the last nibble); `COMP`/`COMP-4`/`COMP-5`/`BINARY` fields
  (big-endian two's-complement/unsigned integers); and plain
  alphanumeric (`PIC X`/`A`) fields as exact fixed-width text —
  trailing-space stripping is opt-in (`strip_trailing_spaces=`), never
  silent, since trimming is a transformation, not a decode — all
  including through nested groups and `REDEFINES`'s shared offsets. It
  does **not yet** decode: `COMP-1`/`COMP-2` (float — no safe default,
  goal.md §5.4), edited pictures or national/DBCS fields, or `OCCURS`
  tables — each raises `UnsupportedDecodeError` rather than guessing.
  A fixed-length record
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
- **`REDEFINES` codegen is struct-shape only for the plain type
  generators** (decision 0005, unrevised for this output): the original
  and redefining items become two independent fields with a comment,
  not a real memory overlay, in `generate_go()`/`generate_java()`. The
  Go flyweight decoder has a real answer now (see its own bullet
  below) — decision 0005 is superseded for that output only, per
  ADR 0009.
- **Go's decimal scale isn't self-describing.** A scaled `int64` field
  (decision 0002) requires the caller to know and apply the scale
  manually — nothing generated computes `value / 10^scale` for you.
- **Sibling-name collisions** aren't handled: two different COBOL
  fields that happen to produce the same generated identifier (e.g.
  `ACCOUNT-ID` and `ACCOUNT_ID` both → `AccountId`) will silently
  collide. Explicitly out of scope per decision 0003, not yet raised
  as its own question.
- **Go flyweight decoder (`emit="decoder"`, ADR 0009, Phase 10) covers
  `DISPLAY`/`COMP-3`/binary records, flat or nested, so far.**
  `generate_go_decoder()` emits a struct per group (root and nested)
  wrapping a `[]byte`, with one accessor method per field reading
  directly from the buffer with zero allocation — `DISPLAY` (unsigned,
  and signed via trailing/leading overpunch or trailing/leading `SIGN
  IS SEPARATE` — a separate sign byte is checked as a literal value
  directly, `0x4E`/`0x60` in `cp037` for `+`/`-`, no charset table
  needed for just two values) via per-field byte/nibble arithmetic;
  `COMP-3`/`PACKED-DECIMAL` via one shared `decodePackedDecimal()`
  helper (emitted once per file, only when needed); `COMP`/`COMP-4`/
  `COMP-5`/`BINARY` via `encoding/binary`'s `BigEndian.Uint16/32/64`,
  sign-extended with a same-width signed cast (reinterpreting the
  two's-complement bit pattern, matching Python's
  `int.from_bytes(signed=True)`). A resolved `big.Int` field (never
  decision 0004's default — the ladder tops out at int64/uint64 — but
  reachable past 18-19 digits, or via a forced override) reuses the
  same DISPLAY/`COMP-3` dispatch with `big.Int` arithmetic and its own
  shared helpers (`decodeDisplayDigitsBig`, `decodePackedDecimalBig`,
  each emitted once per file, only when needed); `big.Int` on a binary
  field raises rather than guessing, since `datatypes/sizing.py`'s
  binary tier already caps at 8 bytes/`uint64` range and this slice
  doesn't need to reach further for that usage. Plain alphanumeric
  (`PIC X`/`A`) fields decode via a hardcoded 256-entry cp037-to-Unicode
  lookup table, embedded as a shared Go helper the same way
  `decodePackedDecimal` is — generated directly from Python's own
  `cp037` codec, not `golang.org/x/text`, so generated Go stays a
  zero-dependency consumer the way every other usage type here already
  is. The accessor returns a plain `string` with no error — the table
  is total, so there's nothing to fail on — and the exact fixed-width,
  space-padded text, matching `decode_alpha()`'s own default (no silent
  trailing-space stripping; trimming is left to the caller). A nested
  group's accessor just hands its parent's `buf` to a new struct value
  (no allocation, no offset arithmetic needed at that level) because
  `FieldNode.offset` is already absolute from the record root (ADR
  0008), not relative to the immediate parent — true for any group
  reachable without ever passing through an `OCCURS` group. `OCCURS`
  (leaf or group) gets an indexed accessor instead: a bounds-checked
  `index int` parameter, and `start := (offset-base) + index*byte_size`
  where `base` is a codegen-time-only value (0 unless the field is
  under an `OCCURS` group, in which case it resets to that group's own
  offset for everything beneath it, however deep — composes correctly
  for `OCCURS` nested inside `OCCURS`, since each level's reslice
  resets the coordinate frame again). An `OCCURS` group's accessor
  reslices `r.buf[start:start+byte_size]` into a fresh struct value —
  still zero allocation, just a slice header — and that reslice is what
  lets the group's own children keep using plain per-occurrence-
  relative offsets with no index baked into their generated bodies.
  Indexing is 0-based, matching `generate_go()`'s own existing
  `[N]Type` array representation for `OCCURS`, not COBOL's 1-based
  subscripts. Plain alphanumeric's non-`OCCURS` accessor has no error
  return (the cp037 table is total), but gains one under `OCCURS`, for
  the bounds check alone. **`REDEFINES` gets a real overlay only when
  the caller explicitly declares how**, via a new `redefines:
  dict[str, RedefinesDispatch]` parameter on `generate_go_decoder()` —
  never inferred, since bare COBOL `REDEFINES` syntax doesn't itself
  name a discriminator the way `variants/config.py`'s own JSON config
  does for a whole-record variant. A `RedefinesDispatch` names a
  sibling discriminator field and a value→variant-name rule list;
  `generate_go_decoder()` then emits a marker interface (one method,
  e.g. `isCardDataOverlay()`), every named view's struct implementing
  it, and one dispatcher method (named after the target) that decodes
  the discriminator and type-switches to the active view's struct,
  sharing the target's own `r.buf` unchanged (`REDEFINES` shares bytes,
  it doesn't reslice) — this is `ADR 0009`'s own named Go mechanism,
  "interface+type-switch." Scoped narrowly: the target and every
  overlaid field named in a rule must be a group (a leaf-level overlay
  is a different, simpler shape left for later); the discriminator must
  be a direct sibling of the target, a single elementary non-`OCCURS`
  field (the same restriction `variants/config.py`'s own
  `validate_variant_config` places on its own discriminator); and
  `REDEFINES` combined with `OCCURS`, on the target, a sibling, or the
  discriminator, still isn't supported. A `REDEFINES` field with no
  `redefines` entry for its target still raises exactly as before this
  parameter existed. `unbolt.decoding`'s own `decode_record()` is
  unaffected by any of this — it still decodes every overlaid view
  independently side by side (Phase 8's own, separately-scoped
  behavior); only `generate_go_decoder()` picks one. It raises
  `UnsupportedDecodeError` (never guesses) for: more than one DSL root;
  a scalar (non-group) root; `REDEFINES` with no dispatch configured
  for its target (checked before `OCCURS` is ever considered); edited/
  national fields; `COMP-1`/`COMP-2` (float); `big.Int` on a binary
  field; and any other resolved Go type outside the plain
  `int8`..`int64`/`uint8`..`uint64`/`big.Int` set (`string` as a forced
  override onto a non-alphanumeric field, a forced `float32`/`float64`
  override). `emit="decoder"` with `target="java"` now exists too, but
  covers far less — see its own bullet below. Verified with real
  round-trips, not just compile checks: `tools/compile_check` builds
  and **runs** eight generated Go decoders (flat `DISPLAY`-only; a
  synthetic `DISPLAY`+`COMP-3`+binary record; the real `nested_groups.cpy`
  fixture, two levels deep; a synthetic record covering all three
  non-default sign placements; a synthetic record covering `big.Int`
  across every supported usage/sign placement; a synthetic record
  covering plain alphanumeric decode; the real `occurs_table.cpy`
  fixture, a leaf `OCCURS` count sibling to a group `OCCURS`, including
  an out-of-range index; and the real `redefines_overlay.cpy` fixture
  dispatched by its `PAYMENT-TYPE` field, including an unmatched
  discriminator value — no existing fixture uses any of the synthetic
  combinations, is wide enough to need `big.Int`, or has a plain
  `PIC X`/`A` field within this slice's scope alone) against real bytes
  in Docker, asserting the decoded values match Python's own
  `decode_record()` exactly (ADR 0009's stated acceptance criterion) —
  except the `OCCURS` case, where `decode_record()` itself doesn't
  support `OCCURS` yet (see "Record decoding" above), so its expected
  values are instead cross-checked against the same leaf-level
  `decode_display()`/`decode_alpha()` primitives applied by hand, per
  occurrence.
- **Java flyweight decoder (`emit="decoder"`, `target="java"`, ADR
  0009, Phase 10) covers `DISPLAY`/`COMP-3`/binary records, flat or
  nested, so far — far narrower than the Go decoder's eight slices.**
  `generate_java_decoder()` emits one public class per DSL root (Java
  allows only one public top-level type per file, the same reason
  `generate_java()` already returns `dict[str, str]` rather than one
  blob — reused unchanged), each wrapping a `java.nio.ByteBuffer` and
  reading via its absolute indexed getters (`get(int)`,
  `getShort`/`getInt`/`getLong(int)` for binary fields), which default
  to big-endian — COBOL's own convention — so, unlike the Go decoder's
  `[]byte` slices, nothing here has ever needed to reslice a buffer.
  `DISPLAY` (unsigned, and signed via trailing/leading overpunch or
  trailing/leading `SIGN IS SEPARATE`) works the same way the Go
  decoder's own fourth slice did; `COMP-3`/`PACKED-DECIMAL` via a
  private static
  `decodePackedDecimal()` helper (emitted once per class, only when
  needed — a direct, duplicated-per-nibble port of Go's own
  `decodePackedDecimal`, since Java has no free functions to share it
  across classes); `COMP`/`COMP-4`/`COMP-5`/`BINARY` reads natively via
  `ByteBuffer`'s own big-endian getters, with no `encoding/binary`-style
  explicit byte-order setup the way Go needed. Java has no unsigned
  primitives, so an unsigned binary field's resolved type widens past
  its native read width via a mask (`& 0xFFFF` for 2 bytes widening to
  `int`, `& 0xFFFFFFFFL` for 4 widening to `long`) — except an unsigned
  8-byte field, which needs no mask at all: confirmed by computing both
  numbers directly (not assumed) that its 18-digit ceiling
  (`datatypes/sizing.py`'s own BINARY tier limit) always fits within
  `long`'s own signed range (`999999999999999999 <
  9223372036854775807`), so there's no wider type to widen into and
  the native `getLong()` read is already correct — this is exactly
  the kind of edge case a real round-trip test exists to catch, and it
  did: an earlier version of this code raised `KeyError` on that exact
  input before the round-trip below caught it. Decode errors throw
  `java.lang.IllegalArgumentException` (unchecked), reusing
  `generate_java()`'s own precedent for its range validators rather
  than a new checked-exception type. A nested group gets its own `public
  static class` textually nested inside its parent — mirroring
  `generate_java()`'s own nested-static-class shape, since Java has no
  floating top-level `static class` the way Go's flat top-level types
  allow — with an accessor returning a fresh instance sharing the same
  `buf` (one small heap allocation per call, unlike Go's zero-
  allocation struct values — a real, documented difference, not
  hidden). Offsets stay absolute from the record root at every nesting
  depth for a plain nested group, exactly as for a flat record — no
  per-instance `base` tracking needed there, since its position is
  fully known at codegen time. A resolved
  `BigInteger` field (never decision 0004's default — `java_rules.py`'s
  own ladder tops out at `long` — but reachable past `long`'s own
  ~19-digit range, or via a forced override) reuses the same
  DISPLAY/`COMP-3` dispatch with `java.math.BigInteger` arithmetic and
  its own shared helpers (`decodeDisplayDigitsBig`,
  `decodePackedDecimalBig`) — a direct port of Go's own big.Int logic,
  except every operation reassigns `v` instead of mutating it in
  place, since `BigInteger` (unlike Go's `big.Int`) is immutable. A
  helper that hits bad input just throws `IllegalArgumentException`
  directly and lets it propagate — there's no Go-style explicit
  `(value, error)` return to thread back up through every caller, so
  every `BigInteger` accessor's body is a single expression or a short
  switch, never an explicit error check. `BigInteger` on a binary
  field raises rather than guessing, for the same reason established
  above (every `BINARY` tier's digit ceiling already fits within its
  own native signed type). Plain alphanumeric (`PIC X`/`A`) fields
  decode via `Charset.forName("Cp037")` — unlike Go, which has no
  EBCDIC codec in its standard library at all (hence its own
  hardcoded 256-entry table), Java's standard library ships `"Cp037"`
  as a real `Charset` (resolving to `"IBM037"`) — confirmed by
  actually running it in a real JDK 21 container and checking its
  output against `decode_alpha()`'s own doctest value, not assumed
  from the name alone. A shared `private static final Charset CP037`
  field is emitted once per class, only when an alphanumeric field
  exists; each accessor copies its own bytes into a small `byte[]`
  (`ByteBuffer` has no absolute bulk-get on every JDK version, so this
  is a plain loop, not a bulk API call) and decodes with `new
  String(bytes, CP037)`. Returns the exact fixed-width, space-padded
  text, matching `decode_alpha()`'s own default (no silent trailing-
  space stripping). `OCCURS` (leaf or group) gets an indexed accessor
  (`int index` parameter, a bounds-checked `IllegalArgumentException`
  — no sentinel return needed, unlike Go's own `(zero, error)` shape,
  since Java's exceptions are unchecked). Every class that is ever
  reached through an `OCCURS` group gains a `private final int base`
  field (via a package-private `(ByteBuffer buf, int base)`
  constructor) meaning "what absolute index does this instance's own
  offset 0 correspond to" — absent on any class never reached through
  `OCCURS`, which keeps the bare-absolute-offset scheme unchanged.
  Entering an `OCCURS` group's children resets this to that group's
  own offset, however deep; a plain nested group passes whatever
  `base` it received straight through. Unlike Go, where a reslice
  already puts byte 0 of a new slice at the right place with zero
  runtime state, Java's `base` field *is* runtime state, since Java
  accessors never reslice — so every DISPLAY sign-placement body that
  does its own offset arithmetic (signed trailing overpunch, leading
  overpunch, either `SIGN IS SEPARATE` form, and their `BigInteger`
  equivalents) needed a second, parallel body generator written in
  terms of runtime-declared `start`/`end` local variables instead of
  codegen-time literals; bodies with no such arithmetic (unsigned
  `DISPLAY`, `COMP-3`, `BINARY`, alphanumeric) needed no second copy,
  since they already just interpolate `start`/`end` wherever they
  appear. Indexing is 0-based, matching `generate_java()`'s own
  `[N]Type` array convention, same as Go's. Not yet supported — each
  raises `UnsupportedDecodeError` rather than guessing: a scalar
  (non-group) root; `REDEFINES`; `COMP-1`/`COMP-2`; edited/national
  fields; `BigInteger` on a binary field; and any other resolved Java
  type outside the plain `byte`/`short`/`int`/`long`/`BigInteger` set
  — `BigDecimal` (every decimal/scaled field's resolved type for
  Java — no analogue to Go's scaled-`int64` marker exists here, so
  this is a different, still-open design question, not a mechanical
  lift), and `String` as a forced override onto a non-alphanumeric
  field. Verified with real round-trips, not just compile checks:
  `tools/compile_check` builds, **runs**, and asserts decoded values
  from seven generated decoders (a synthetic flat `DISPLAY`-only
  record reusing `flat_display.cpy`'s own two integer fields, minus
  its decimal `ACCOUNT-BALANCE` field, which is out of this slice's
  scope; a synthetic `DISPLAY`+`COMP-3`+binary record including that
  unsigned 8-byte `BINARY` field; a synthetic record mirroring
  `nested_groups.cpy` two levels deep; a synthetic record covering all
  three non-default sign placements; a synthetic record covering
  `BigInteger` across every supported usage/sign placement; a
  synthetic record covering plain alphanumeric decode; and the real
  `occurs_table.cpy` fixture, a leaf `OCCURS` count sibling to a group
  `OCCURS`, including an out-of-range index — the last four reusing
  the Go decoder's own `sign_placements`/`bigint`/`alpha`/
  `occurs_table.cpy` sources and bytes directly) inside a real JVM
  (`eclipse-temurin:21-jdk`), cross-checked against Python's own
  `decode_record()` first — except the `OCCURS` case, where
  `decode_record()` itself doesn't support `OCCURS` yet (see "Record
  decoding" above), so its expected values are instead cross-checked
  against the same leaf-level `decode_display()`/`decode_alpha()`
  primitives applied by hand, per occurrence, same as the Go
  decoder's own `OCCURS` round-trip.

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
- **`unbolt check`/`check_compatibility` only compare a copybook's
  first root** (`dsl.roots[0]`) — a copybook with multiple `01`/`77`
  top-level items only has its first one checked; multi-root support
  isn't implemented.
- **Variant config + runtime dispatch (decision 0012) is library-only,
  no CLI/MCP wrapper.** `load_variant_config()`, `validate_variant_config()`
  (now also checking the discriminator field is a single elementary
  item — not a group, not `COMP-1`/`COMP-2`, not an `OCCURS` table —
  and has the *identical* offset/byte size/PIC/usage/sign across every
  variant, since dispatch has to read it before knowing which full
  layout applies), and `select_variant()` (decodes a real discriminator
  value and dispatches to the matching variant's `decode_record()`,
  `UnknownVariantError`/passthrough per the config's policy) all exist
  and are tested. There's no `unbolt`-CLI-command or MCP-tool wrapper
  for this yet — consistent with `decode_record()`/`decode_rdw_record()`
  themselves, which have never had one either; all of `unbolt.decoding`
  and `unbolt.variants`' dispatch are library-only so far. `unbolt check`
  (the one variant-adjacent CLI command/MCP tool that does exist) still
  always compares exactly two whole copybook files directly; it doesn't
  consult a variant config.
- **Rename matching is name-only.** `select_variant()`'s discriminator
  match is purely `decoded_value == rule.value` (Decimal-normalized for
  numeric fields, exact string for alphanumeric) — there's no fuzzy or
  case-insensitive matching, and a numeric discriminator's rule value
  that isn't valid decimal text never matches anything (silently, by
  design: an invalid comparison target is not the same claim as "this
  variant"), rather than raising at dispatch time. If every rule's
  value is malformed this surfaces as `UnknownVariantError`/passthrough,
  not a clearer "config error," since dispatch doesn't re-validate
  value parseability per decoded type — only `load_variant_config()`'s
  shape checks run ahead of time.

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

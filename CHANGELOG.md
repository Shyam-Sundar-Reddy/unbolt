# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Phase 8 (local docs/phase.md), first slice: `FieldNode.offset` — every
  field's byte offset within its parent, computed in `build_dsl()`
  alongside `byte_size`/`digits`/`scale` (ADR 0008, in the local
  `docs/decisions/`). An `OCCURS` field's offset marks where its first
  occurrence starts; a `REDEFINES` field shares its target's offset and,
  if wider, pushes later siblings' offsets to cover the real extent —
  the same math `_group_byte_size` already used for the record's total
  size, now applied per field. `DSL_VERSION` bumped `"0"` → `"1"`; every
  golden DSL fixture regenerated with hand-verified offsets. 6 new
  tests (`tests/test_dsl_offsets.py`), including the REDEFINES-wider-
  than-its-target case no existing fixture exercised.
- Phase 8, second slice: `unbolt.decoding` — `decode_record()` decodes
  real bytes into real field values for plain `DISPLAY` (zoned decimal)
  fields, unsigned and signed via EBCDIC overpunch (`cp037` default,
  explicit override allowed; decision 0010, local `docs/decisions/`),
  through nested groups and across `REDEFINES`'s shared offsets. A
  record whose length doesn't match its layout is rejected
  (`RecordLengthMismatchError`), never best-effort decoded. `COMP`/
  packed/binary/float, `SIGN IS SEPARATE`, alphanumeric/edited/
  national, and `OCCURS` fields each raise `UnsupportedDecodeError`
  rather than guessing — later Phase 8 slices. 17 new tests
  (`tests/test_decoding_codecs.py`, `tests/test_decoding_record.py`),
  including a full hand-crafted-bytes decode of two real fixtures
  compared against hand-computed expected values — the round-trip
  guarantee (goal.md §7) tested against actual bytes for the first
  time, not just ranges.
- Phase 8, third slice: `COMP-3`/`PACKED-DECIMAL` decode —
  `decode_packed()` reads two digits per byte with the sign in the last
  nibble (same C/D/F convention as DISPLAY overpunch, applied to a
  whole nibble rather than combined with a digit); an even digit count's
  standard leading zero-pad nibble is validated, not just skipped. New
  `datatypes.sizing.is_packed_usage()` so `decoding/record.py` doesn't
  duplicate the `{"COMP-3", "PACKED-DECIMAL"}` set `numeric_byte_size()`
  already has. 11 new tests, including `mixed_usage.cpy`'s real
  `TRANSACTION-COUNT`/`UNIT-PRICE` fields decoded against hand-computed
  values, and a full end-to-end `decode_record()` mixing `COMP-3` and
  `DISPLAY` fields in one record.
- Phase 8, fourth slice: `COMP`/`COMP-4`/`COMP-5`/`BINARY` decode —
  `decode_binary()` reads a plain big-endian two's-complement (signed)
  or unsigned integer; mechanically identical for all four usages,
  since decision 0001's `COMP-5` exception (full native binary range
  vs. `TRUNC(STD)`'s PIC-limited range) is a range/validation policy,
  not a byte-decode difference. New `datatypes.sizing.is_binary_usage()`
  alongside `is_packed_usage()`. 5 new tests, including
  `mixed_usage.cpy`'s real `RECORD-ID`/`LARGE-ID`/`TRANSACTION-COUNT`/
  `UNIT-PRICE`/`HUGE-VALUE` fields all decoding correctly end to end
  (only `COMP-1`'s `SENSOR-READING` still raises, confirming the
  earlier fields don't fail prematurely).
- Phase 8, fifth slice: `SIGN IS SEPARATE`/`SIGN IS LEADING` decode —
  new `FieldNode.sign_leading` (DSL v2) so the DSL actually tracks what
  `parser.py` already parsed but previously discarded. `decode_display()`
  now handles all four sign placements: trailing overpunch (COBOL's
  default), leading overpunch, trailing separate, and leading separate
  — a separate sign is a plain `+`/`-` byte decoded normally through
  the codepage, never confused with overpunch's byte-value convention.
  7 new tests (net, after retiring the now-obsolete "SIGN IS SEPARATE
  isn't supported yet" test), including two real `decode_record()` runs
  confirming
  `sign_leading` flows correctly from the parser through the DSL to
  decode, not just `decode_display()` in isolation.
- Phase 8, sixth and final slice: `decode_rdw_record()` — parses and
  validates a 4-byte RDW (Record Descriptor Word) variable-length-
  record header (big-endian total length including the header itself,
  reserved bytes must be zero — non-zero marks a spanned record,
  which isn't supported), then hands the extracted payload to the
  existing `decode_record()` unchanged. Verified against IBM's own
  documented RDW format before implementing, not assumed. RDW framing
  is additive — it doesn't relax decision 0010's exact-length-match
  rule for the payload, it only tells you where one record ends inside
  a larger buffer (e.g. ignoring a following record's bytes). New
  `RdwHeaderError` for a malformed header. 7 new tests, including a
  real fixture's bytes wrapped in a correct RDW decoding identically
  to the unwrapped call, and trailing bytes after the declared length
  being correctly ignored. This closes out Phase 8 (goal.md §7,
  phase.md Phase 8): real byte-level decoding for DISPLAY, COMP-3,
  binary, all four sign placements, and RDW framing.
- Phase 9 (local docs/phase.md), first slice: `unbolt.variants.
  classify_compatibility()` — FULL/FORWARD/BACKWARD/BREAKING for two
  versions of the same record, per decision 0011 (worked out, not
  guessed: COBOL records are positional, so Avro's own backward/
  forward rules needed reframing — a purely-trailing field addition is
  FORWARD-only, a purely-trailing removal is BACKWARD-only, since
  COBOL's fixed-offset model has no default-value mechanism to make a
  trailing addition safe for an old-data reader). Any reordering,
  middle insertion/removal, or in-place change to a shared field's
  offset/size/type/scale is BREAKING. New `dsl.walk.walk_from()` (a
  single-root walk, factored out of `walk_fields()` for reuse here).
  12 new tests, including a regression for a real bug caught before
  trusting the implementation: a group's own `byte_size` naturally
  grows when a trailing child is added, which the first version wrongly
  flagged as a breaking change on the group itself; group/leaf
  signature comparison now excludes derived fields. No CLI command or
  YAML variant config yet — see `docs/limitations.md`.
- Phase 9, second slice: `unbolt check old.cpy new.cpy [--mode
  backward|forward|full]` (CLI) and `check_compatibility(old_file,
  new_file, mode=None)` (MCP tool) — both thin wrappers over
  `classify_compatibility()`; a new `satisfies_mode()` in
  `unbolt.variants` is the single shared place both the CLI and MCP
  tool ask "does this verdict meet what was requested," so they can't
  drift apart. Without `--mode`/`mode`, `check` only reports (exit code
  0 regardless of verdict); with it, a verdict that doesn't satisfy the
  mode raises `IncompatibleChangeError` (non-zero CLI exit), so this can
  gate a CI step. `docs/cli.md`/`docs/mcp.md` updated with real captured
  output; `goal.md` §10 updated (8 MCP tools, 8 CLI commands). 6 new
  tests. Still only compares a copybook's first root
  (`dsl.roots[0]`) — no multi-root or YAML variant/discriminator
  support yet, see `docs/limitations.md`.
- Phase 9, third slice: variant config — `load_variant_config()`/
  `validate_variant_config()` in `unbolt.variants.config`. Closes two
  open decisions: goal.md §8 Q14 (discriminator ownership — in-record/
  self-describing, since unbolt has no Kafka topic/subject integration
  anywhere in scope) and the config format (JSON, not the originally-
  planned YAML — zero new dependencies, same pattern
  `.unbolt-overrides.json` already uses; decision 0012). Validates
  shape (required keys, `unknown_variant` ∈ `{"reject","passthrough"}`,
  unique variant names/values) and, separately, cross-checks a loaded
  config against real parsed copybooks (discriminator field present
  and unambiguous in every referenced variant). New
  `InvalidVariantConfigError`. 16 new tests. This is load/validate
  only — runtime variant selection (decode a real discriminator value,
  dispatch, `UnknownVariant` fallback) is genuinely blocked on
  alphanumeric field decode, which `unbolt.decoding` doesn't have yet;
  see `docs/limitations.md`. Also revises ADR 0008: the
  `Dsl.variant`/`Dsl.schema_version` fields it deferred to this phase
  turned out not needed — variant identity lives in the config's own
  `VariantRule`, not embedded in `Dsl`.
- Phase 9, fourth slice: alphanumeric (`PIC X`/`A`) field decode —
  `decode_alpha()` in `unbolt.decoding`, exact fixed-width text
  through the codepage; trailing-space stripping is opt-in
  (`strip_trailing_spaces=`, default `False`), never silent, since
  trimming is a transformation, not a decode. Closes a real gap left
  open since Phase 8 (alphanumeric was explicitly out of scope there)
  and the actual blocker for decoding a real `PIC X` discriminator
  value from bytes. 7 new tests, including `redefines_overlay.cpy` —
  a real fixture that couldn't fully decode before this slice because
  it starts with an alphanumeric field — now decoding completely end
  to end, including both `REDEFINES` siblings correctly reading their
  own view of the same shared bytes.
- Phase 9, fifth slice — **Phase 9 complete**: runtime variant
  dispatch. `unbolt.variants.select_variant(config, dsls, data)`
  decodes the discriminator field directly, matches it against each
  rule's value (`Decimal`-normalized for a numeric discriminator —
  `"01"` and `"1"` match the same rule — exact string for
  alphanumeric), and dispatches to the matched variant's own
  `decode_record()`. No match: `UnknownVariantError` or a
  `VariantSelection` with the raw bytes preserved, per the config's
  own `unknown_variant` policy, never an implicit default.
  `validate_variant_config()` (which `select_variant()` always runs
  first, never skippable) now also requires the discriminator to be a
  single elementary field — not a group, `COMP-1`/`COMP-2`, or an
  `OCCURS` table — with an *identical* offset/byte size/PIC/usage/sign
  across every variant, since dispatch reads it before knowing which
  full layout even applies. New shared `decode_field()` in
  `unbolt.decoding` (factored out of `decode_record()`'s per-leaf
  dispatch) so the full-record walk and this discriminator-only decode
  use exactly the same decodability rules. New `UnknownVariantError`.
  8 new tests. No CLI/MCP wrapper yet, consistent with
  `decode_record()`/`decode_rdw_record()` themselves — see
  `docs/limitations.md`.
- Phase 10, first slice: `generators/go_decoder.py`'s
  `generate_go_decoder(dsl, resolved)` — a flyweight Go decoder (ADR
  0009): a struct wrapping `[]byte`, one accessor method per field
  reading straight from the buffer at its offset, zero allocation,
  zero reflection. Scoped as narrowly as Phase 8's own first slice:
  flat records only, `DISPLAY` fields only (unsigned + signed trailing
  overpunch), plain integer-ladder Go types only. Reuses the exact Go
  type `recommend_mappings`/`resolve_mapping` already chose, so this
  and the plain-struct generator agree on every field's type. Wired
  into `generate_code()` via a new `emit` parameter (`"types"` default,
  `"decoder"` new); `target="java"` + `emit="decoder"` raises clearly
  — no Java decoder generator yet. `tools/compile_check` now builds
  *and runs* the generated decoder in a real `golang:1.23` Docker
  container against the exact bytes the Python-side decoder's own test
  already used, asserting both independently-written decoders agree
  on every value (ADR 0009's round-trip acceptance criterion). 19 new
  tests.
- Phase 10, second slice: lifted the Go flyweight decoder's
  `COMP-3`/`PACKED-DECIMAL` and `COMP`/`COMP-4`/`COMP-5`/`BINARY`
  restrictions. Packed decimal decodes via one shared
  `decodePackedDecimal()` helper (emitted once per file, only when
  needed) replicating `decode_packed()`'s nibble/pad/sign logic
  exactly; binary fields read via `encoding/binary`'s
  `BigEndian.Uint16/32/64`, sign-extended with a same-width signed Go
  cast. Caught and fixed before trusting it: an early version emitted
  a redundant double-cast (`int32(int32(...))`) when the resolved type
  already matched the natural sign-extension type — found by actually
  reading the generated Go, not by assuming the string-building logic
  was right. `tools/compile_check` gained a second real round-trip —
  a synthetic `DISPLAY`+`COMP-3`+binary record, since no existing
  fixture combines all three within this slice's scope — with its
  expected bytes hand-computed and cross-checked against
  `decode_record()` directly first; this caught one wrong guessed byte
  sequence for the binary field's expected encoding before it ever
  reached Docker. 5 new tests.
- Phase 10, third slice: nested-group support for the Go flyweight
  decoder. A group field now gets its own Go struct type, mirroring
  `generate_go()`'s nested-struct shape; the parent's accessor for it
  just hands over the same `buf` reference to a new struct value — no
  allocation, no offset math needed at that level, since
  `FieldNode.offset` is already absolute from the record root (ADR
  0008), not relative to the immediate parent. `OCCURS`/`REDEFINES`
  are rejected the same way whether they land on a group or a leaf.
  `tools/compile_check` gained a third real round-trip: the real
  `nested_groups.cpy` fixture (two levels deep), its expected bytes
  hand-computed and cross-checked against `decode_record()` directly
  first. 4 new tests (net, after retiring the now-obsolete "nested
  group isn't supported" test).
- Phase 10, fourth slice: `SIGN IS SEPARATE`/`SIGN IS LEADING` support
  for the Go flyweight decoder, mirroring Phase 8's own DISPLAY
  sign-placement step. Leading overpunch and both separate-sign forms
  each get their own Go body generator; a separate sign byte is
  checked as a literal value directly (`0x4E`/`0x60` in `cp037` for
  `+`/`-`) rather than needing a full charset table. `tools/
  compile_check` gained a fourth real round-trip: a synthetic record
  covering all three non-default sign placements, its expected bytes
  hand-computed and cross-checked against `decode_record()` directly
  first. 1 new test (net, after retiring two now-obsolete
  "unsupported" tests and adding three real ones).
- Phase 10, fifth slice: `big.Int`/wider-type support for the Go
  flyweight decoder. A resolved `big.Int` field (reachable past
  18-19 digits, or via a forced override) reuses the same per-usage
  dispatch as the fixed-width types, with its own shared Go helpers —
  `decodeDisplayDigitsBig()` for plain-digit accumulation across all
  five DISPLAY sign-placement bodies, and a separate
  `decodePackedDecimalBig()` for `COMP-3` (kept distinct from the
  int64 helper so the common/small case doesn't pay `big.Int`
  overhead). `COMP`/`COMP-4`/`COMP-5`/`BINARY` never needs `big.Int` —
  `datatypes/sizing.py`'s binary tier already caps at 8 bytes/`uint64`
  range — so a forced `big.Int` override on a binary field now raises
  rather than guessing. `tools/compile_check` gained a fifth real
  round-trip: a synthetic record with one field per supported usage/
  sign placement, each wide enough (19-20 digits) to genuinely need
  `big.Int`, its expected bytes hand-computed and cross-checked
  against `decode_record()` directly first. 6 new tests (net, after
  retiring the now-obsolete "big.Int isn't supported" test and adding
  seven real ones).
- Phase 10, sixth slice: plain alphanumeric (`PIC X`/`A`) decode for
  the Go flyweight decoder. Python's `decode_alpha()` gets `cp037` for
  free from its standard library, but Go's stdlib has no EBCDIC codec
  at all, so this slice's real decision was hardcode-a-table vs. add
  `golang.org/x/text` as a dependency for every consumer of generated
  Go code - resolved in favor of hardcoding. The 256-entry
  `cp037ToUnicode` lookup table is generated directly from Python's own
  `cp037` codec, never typed by hand, and embedded as a shared Go
  helper the same way `decodePackedDecimal` is. The accessor returns a
  plain `string` with no error return (the table is total - every byte
  decodes to something) and the exact fixed-width, space-padded text,
  matching `decode_alpha()`'s own default. `tools/compile_check` gained
  a sixth real round-trip: a synthetic record mixing letters,
  digits-as-text, and trailing-space padding, its expected bytes
  hand-computed via Python's own `cp037` codec and cross-checked
  against `decode_record()` directly first. 3 new tests (net, after
  retiring the now-obsolete combined "alphanumeric/edited/national"
  test and adding four real ones).
- Phase 10, seventh slice: `OCCURS` support (leaf and group fields) for
  the Go flyweight decoder. Every accessor now threads a codegen-time
  `base` value (never a runtime struct field) meaning "what absolute
  offset does this struct's buf[0] correspond to" - 0 everywhere a
  struct is reachable without ever passing through an `OCCURS` group
  (every struct that existed before this slice, so existing generated
  output is unchanged), reset to that group's own offset for everything
  beneath it otherwise. A leaf under `OCCURS` gains an `index int`
  parameter and a bounds check; a group under `OCCURS` reslices
  `r.buf[start:start+byte_size]` into a fresh struct value (still zero
  allocation), which is what lets the group's own children keep
  emitting plain per-occurrence-relative offsets with no index baked
  into them. Composes correctly for `OCCURS` nested inside `OCCURS`.
  Indexing is 0-based, matching `generate_go()`'s own existing
  `[N]Type` array convention. `tools/compile_check` gained a seventh
  real round-trip: the real `occurs_table.cpy` fixture, including an
  out-of-range index - since `decode_record()` doesn't support `OCCURS`
  yet, its expected bytes were cross-checked against the same
  leaf-level `decode_display()`/`decode_alpha()` primitives applied by
  hand per occurrence, rather than against `decode_record()` as a
  whole. 4 new tests (net, after retiring two now-obsolete "OCCURS
  isn't supported" tests and adding six real ones).
- Phase 10, eighth slice: `REDEFINES` as a real overlay for the Go
  flyweight decoder (ADR 0009's own promise). Phase 9's
  `select_variant()` couldn't be reused directly - it dispatches across
  separate whole copybooks, not siblings within one record - so this
  ships a new, smaller, purpose-built `redefines:
  dict[str, RedefinesDispatch]` parameter on `generate_go_decoder()`
  (library-only for now, same sequencing Phase 9 itself used). For each
  configured target, the generator emits every named view's struct
  (including REDEFINES siblings, which previously never got rendered
  at all), a marker interface (one unexported method, e.g.
  `isCardDataOverlay()`), and one dispatcher method - named after the
  target, replacing what would have been its own plain accessor - that
  decodes a sibling discriminator and type-switches to the active
  view, sharing the target's own `r.buf` unchanged. This is ADR 0009's
  own named mechanism, "interface+type-switch." Scoped to group-level
  overlays only (leaf-level is a different, simpler shape, left for
  later); the discriminator must be a direct sibling, a single
  elementary non-`OCCURS` field; `REDEFINES` combined with `OCCURS`
  still isn't supported. A numeric discriminator's rule values are
  normalized to canonical decimal literals before being emitted as Go
  `case` labels, to avoid Go's leading-zero-means-octal literal syntax.
  A `REDEFINES` field with no `redefines` entry for its target still
  raises exactly as before. `tools/compile_check` gained an eighth real
  round-trip: the real `redefines_overlay.cpy` fixture dispatched by
  its own `PAYMENT-TYPE` field, including an unmatched discriminator
  value - cross-checked against `decode_record()` directly, which
  already decodes both overlaid views independently (picking which one
  is "active" is exactly the new behavior only the Go side has now).
  9 new tests (net - a clean addition, no existing tests needed
  changes).
- Phase 10, ninth slice: the Java flyweight decoder starts
  (`generators/java_decoder.py`), scoped as narrowly as the Go
  decoder's own first slice was - one public class per DSL root (Java
  allows only one public top-level type per file, matching
  `generate_java()`'s own `dict[str, str]` return shape), flat records
  only, `DISPLAY` fields only (unsigned + signed trailing overpunch),
  and only `byte`/`short`/`int`/`long`. Each class wraps a
  `java.nio.ByteBuffer`, reading via its absolute indexed getters
  (`get(int)`, big-endian by default - COBOL's own convention), so
  this slice never needs Go's own buffer-reslicing scheme. Decode
  errors throw `java.lang.IllegalArgumentException` (unchecked),
  reusing `generate_java()`'s own precedent for its range validators.
  Java's integer ladder has no unsigned types and no "scaled-int64"
  marker - a decimal/scaled field resolves straight to `"BigDecimal"`
  for Java, a structurally heavier type excluded from this slice on
  purpose rather than forced through Go's own int-ladder shortcut.
  `generate_code(..., emit="decoder")` now routes `target="java"` to
  this generator instead of raising; an unknown `target` under
  `emit="decoder"` now raises `UnknownTargetError`, matching
  `emit="types"`'s own behavior, replacing the old blanket "only
  supports target='go'" message. `tools/compile_check` gained a first
  Java decoder round-trip, built and actually run (not just compiled)
  inside a real `eclipse-temurin:21-jdk` JVM, reusing `flat_display.cpy`'s
  own two integer fields and their already-verified bytes. 19 new tests
  (`tests/test_generators_java_decoder.py`,
  `tests/test_generators_engine.py`).
- Phase 10, tenth slice: `COMP-3`/`PACKED-DECIMAL` and
  `COMP`/`COMP-4`/`COMP-5`/`BINARY` for the Java flyweight decoder,
  mirroring `go_decoder.py`'s own second slice. `COMP-3` decodes via a
  private static `decodePackedDecimal()` helper (emitted once per
  class, only when needed) - a direct port of Go's own nibble/pad/sign
  logic. `BINARY` fields read via `ByteBuffer`'s own big-endian
  `getShort`/`getInt`/`getLong(int)`. An unsigned field's resolved
  type widens past its native read width via a mask - except an
  unsigned 8-byte field, which needs none: a real round-trip test
  caught a `KeyError` on exactly that case before it shipped (the
  initial code assumed it would need the same masking pattern one
  step further; it doesn't, since its 18-digit ceiling always fits
  within `long`'s own signed range). `tools/compile_check` gained a
  second Java decoder round-trip, including that unsigned 8-byte
  field, built and actually run inside a real `eclipse-temurin:21-jdk`
  JVM. 5 new tests (net, after retiring the now-obsolete "non-DISPLAY
  usage isn't supported" test and adding six real ones).
- Phase 10, eleventh slice: nested groups for the Java flyweight
  decoder, mirroring `go_decoder.py`'s own third slice - simpler than
  first expected: a plain (non-`OCCURS`) nested group's position is
  fully known at codegen time, so no per-instance `base` field is
  needed yet (that's deferred to the slice that actually introduces
  `OCCURS`, where a runtime index genuinely shifts a position - this
  module's own docstring previously assumed `base` would be needed
  here too; corrected after actually working through it). A nested
  group gets its own `public static class`, textually nested inside
  its parent (mirroring `generate_java()`'s own nested-static-class
  shape), with an accessor returning a fresh instance sharing the same
  `buf` - one small heap allocation per call, a real and now-documented
  difference from Go's zero-allocation struct values. `tools/compile_check`
  gained a third Java decoder round-trip, mirroring `nested_groups.cpy`
  two levels deep and reusing bytes already cross-checked for the Go
  decoder's own equivalent round-trip, built and actually run inside a
  real `eclipse-temurin:21-jdk` JVM. 3 new tests (net, after retiring
  the now-obsolete "nested group isn't supported" test and adding two
  real ones).

## [0.1.1] - Released 2026-10-25

### Fixed

- `override` silently accepted a candidate the mapping engine itself had
  already marked `invalid` (e.g. Java `double` for a decimal field,
  rejected by the never-float-for-decimal hard rule; or an integer type
  too narrow for the field's range) without `--force`. The guard was
  built from `candidate_names()`, which returns every candidate
  regardless of status; new `valid_candidate_names()` (status=='valid'
  only) is what `cmd_override`/`update_mapping_override` use now.
- `validate` reported no findings for a field with such an invalid
  override, because the check only asked "does this field have *any*
  valid candidate at all" rather than "is what was actually chosen
  valid." `validate_conversion()` now takes the overrides and checks the
  resolved choice directly, raising a new `forced-invalid-override`
  finding when it isn't.
- The traceability report printed a rejected candidate's own rejection
  rationale as if it were the acceptance reason — e.g. naming `double`
  as the chosen type right next to "rejected by default (hard rule)."
  The report now traces a forced/invalid override to the developer's
  own stated reason, with the rule engine's verdict kept as labeled
  context, not disguised as the acceptance rationale.
- `PIC N(n)`/`PIC G(n)` (national/DBCS) parsed with zero diagnostics and
  silently sized as `digits=0`/`byte_size=0` — neither `is_alpha_pic` nor
  `is_edited_pic` recognizes `N`/`G`, so it fell through to the plain
  numeric path. New diagnostic `CBL-W060`; the field is now sized as
  double-byte text width and excluded from numeric mapping/generation,
  same pattern as `CBL-W050` for edited pictures.

## [0.1.0] - Released 2026-10-24

### Added

- Phase 7 (docs/phase.md): hardening, docs, CI, demo — the last phase
  before this release. Reference docs (`supported-constructs.md`,
  `dsl-spec.md`, `mapping-rules.md`, `diagnostics.md`, `cli.md`,
  `mcp.md`, `performance.md`) are now public; README rewritten with
  real captured CLI/library/MCP output (not mocked), an animated
  terminal demo GIF (`docs/cli-demo.gif`, built with HyperFrames,
  showing the real `parse → recommend → generate → report` pipeline);
  `CONTRIBUTING.md`; `examples/quickstart.py` (a runnable version of
  the README demo, checked in CI); `docs/limitations.md` (an honest
  gap list, written by actually running the behaviors it describes);
  `docs/index.md`. New CI docs job (`tools/check_docs.py`, stdlib
  only): every relative markdown link in tracked docs resolves, and
  the two fully-reproducible generated docs match their generator's
  current output.
- 14 new tests (199 total): docs-check regression tests, the examples
  smoke test, an edited-picture test suite.

### Fixed

- `supported-constructs.md` had two stale/false claims, caught by
  actually running the behavior it described rather than rereading the
  code: `COMP-5` was documented as diagnostic-only but was already
  fully supported (correct byte-size tier and full binary range);
  level 88 (condition names) wrongly fell into the same "no PIC, no
  children" branch `COMP-1`/`COMP-2` uses and got a misleading
  "needs a float policy" mapping candidate instead of being excluded
  as pure metadata.
- Edited `PICTURE` symbols (`Z`, `*`, `$`, `,`, `.`, `+`, `-`, `CR`,
  `DB`) weren't recognized anywhere — the digit-counting regex only
  matches `9`/`A`/`X`, so a field like `PIC ZZ,ZZ9.99` silently
  produced `digits=3` (only the literal `9`s) with no diagnostic at
  all, a direct violation of the "never silently convert" hard rule.
  New `CBL-W050` diagnostic; the field is now sized as text width and
  excluded from numeric mapping, matched at every layer that assumed
  "has a PIC, isn't alphanumeric" meant numeric (`dsl/builder.py`,
  `mapping/engine.py`, `datatypes/sizing.py`'s `describe_datatype()`,
  both generators, `performance/estimate.py`).
- `BLANK WHEN ZERO` was silently consumed with no diagnostic at all,
  inconsistent with `JUSTIFIED`'s existing `CBL-I101`. New `CBL-I103`.
- A real new-developer smoke test (clone fresh, follow only the
  README) caught two bugs every local run had masked: `uv run pytest`
  — exactly what `ci.yml` runs — failed on a clean checkout
  (`ModuleNotFoundError: No module named 'tests'`, fixed with
  `tests/__init__.py` / `tests/bench/__init__.py`), and three docs
  links (`CONTRIBUTING.md`, `CHANGELOG.md`, `supported-constructs.md`)
  only resolved locally, pointing at gitignored files absent from any
  real clone — `tools/check_docs.py` itself only checked filesystem
  existence, not whether a link's target would survive a real
  checkout; fixed to check `git check-ignore` too.

- Phase 6 (docs/phase.md): `estimate_storage()` (`src/unbolt/performance`)
  - theoretical per-record size, always labeled "estimated", target
  bytes left as `None` (never guessed) for variable-size types.
  `run_benchmarks()` - stdlib-only timing harness (not
  `pytest-benchmark`: not worth a new dependency), records the
  environment alongside every timing. `docs/performance.md` generated
  from real runs at 100/1k/10k synthetic field counts plus estimates
  for the real fixtures, with a dated first measurement and an
  explicit note on why a CI regression budget isn't wired in yet (no
  second data point exists to regress against). 15 new tests (185 total).
- Phase 5 (docs/phase.md): the CLI (`unbolt` entry point,
  `src/unbolt/cli.py`, stdlib `argparse`) - `parse`, `dsl`, `recommend`,
  `override`, `generate`, `validate`, `report`, `mcp`. Overrides persist
  across separate CLI invocations via a JSON file (decision 0007,
  `.unbolt-overrides.json` by default). The MCP server
  (`src/unbolt/mcp_server.py`, FastMCP over stdio, behind the new
  `[mcp]` extra) exposes the same 7 core functions as tools, sharing
  the same override file with the CLI. `unbolt mcp` lazily imports
  `fastmcp` so the base install doesn't need the `[mcp]` extra unless
  actually used. Verified against both live - the CLI by running
  every command end to end, the MCP server via `fastmcp`'s own
  in-memory `Client` through a full override -> generate -> validate
  -> report sequence - before writing either's tests. 21 new tests
  (170 total).
- Phase 4 (docs/phase.md): `validate_conversion()` (completeness,
  boundary/precision self-consistency, needs-policy and rolled-up
  parser diagnostics, all as data - `src/unbolt/validation`) and
  `build_report()` + `render_markdown()`/`render_json()`
  (`src/unbolt/reporting`) - a field's source line, chosen type, and
  the rule/rationale that won are now traceable from one report, not
  from reading generator code. `docs/diagnostics.md` generated from a
  new `DIAGNOSTIC_CATALOG` co-located with the diagnostic factory
  functions. 23 new tests (146 total), including a completeness check
  across all 5 Phase-0 fixtures x both targets.
- Phase 3 (docs/phase.md): Go struct and Java POJO code generation
  (`src/unbolt/generators`) - naming (decision 0003: Java reserved-word
  collisions auto-suffixed `_` with an info diagnostic), default
  candidate resolution (decision 0004), `REDEFINES` as two separate
  fields with a comment since no byte decoder exists yet to need real
  memory aliasing (decision 0005), Java style POJO (decision 0006).
  `generate_code(dsl, mapping, target, overrides=...)` ties it
  together, returning `{path: content}`. Range-validator functions
  emitted per field whose type is wider than its PIC range.
  `tools/compile_check`: compiles generated output with real Go/Java
  toolchains via Docker (dev-only) - caught 3 real bugs (nested Java
  classes/validators rendered outside their enclosing braces, missing
  Go imports, missing Java `L` suffix on large `long` literals) that
  string-matching unit tests missed. 36 new tests (123 total).

### Fixed

- `recommend_mappings()` silently omitted `COMP-1`/`COMP-2` fields from
  the `MappingReport` instead of flagging them (goal.md §5.4: IBM
  hexadecimal floating point, not IEEE 754, needs an explicit policy -
  never silent omission). Caught while building Phase 3's generator,
  which needed every field to actually appear in the report.

### Added

- Phase 2 (docs/phase.md): the mapping engine (`src/unbolt/mapping`) -
  Go and Java integer-type ladders (goal.md §5.7's boundary table,
  cross-language-tested: Java's lack of unsigned types verified to need
  a wider type than Go for the same field), decimal rules (Go: scaled
  `int64` per decision 0002, falling back to `string` on overflow; Java:
  always `BigDecimal`, float/double always rejected). `recommend_mappings()`
  returns every candidate with a status and rationale, never just a
  winner. `src/unbolt/overrides`: `apply_override()` stores a developer's
  type choice apart from the DSL, rejecting a choice that isn't among the
  field's candidates unless force-flagged. 21 new tests.
- Phase 1 (docs/phase.md): a real tokenizer, entry/clause parser, and
  level-number tree builder (`src/unbolt/parser`); PIC/USAGE sizing and
  range math for DISPLAY, COMP-3/PACKED-DECIMAL, COMP/COMP-4/BINARY,
  COMP-5, and COMP-1/COMP-2 (`src/unbolt/datatypes`); `build_dsl()` and
  `Dsl.to_json()`/`Dsl.from_json()` (`src/unbolt/dsl`). Stable diagnostic
  codes for unsupported syntax (level 66, `OCCURS ... DEPENDING ON`,
  `COPY ... REPLACING`) instead of crashing or silently dropping them.
  47 tests: per-construct parser tests, diagnostic tests, datatype
  boundary tests, and golden DSL JSON for all 5 Phase-0 fixtures.

## [0.0.1] - Released

### Added

- Initial package scaffold: `src/unbolt` layout, `pyproject.toml` metadata
  (Apache-2.0, `requires-python >=3.12`), CI (`ci.yml`: tests + ruff + mypy)
  and publish (`publish.yml`: PyPI on tag push) workflows, logo and
  wordmark SVGs, README, LICENSE.
- No parser/DSL/mapping code yet — see the (local-only) design doc for
  the phase plan.

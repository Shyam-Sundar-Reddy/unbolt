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

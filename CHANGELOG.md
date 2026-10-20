# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

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
- No parser/DSL/mapping code yet — see [docs/goal.md](docs/goal.md) for
  the phase plan.

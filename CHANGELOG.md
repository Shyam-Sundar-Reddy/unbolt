# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

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

# CLAUDE.md — Unbolt

Read [docs/goal.md](docs/goal.md) first. It is the source of truth for scope, architecture and phases. Section references below ("GOAL.md section N") refer to that file.

## Mission
Parse COBOL copybooks → versioned DSL → explainable Go/Java type mapping → deterministic code + traceability.
Delivered as a Python package, a CLI and an MCP server. Preserve first, explain every decision, optimize only with evidence.

## How to work
1. Work ONE phase at a time (GOAL.md section 6). Before coding, state: objective, files/modules to touch, key decisions, acceptance tests. Then implement only that phase and stop for review.
2. Tests first for parsing, mapping and boundaries. Add golden-file tests for generated output.
3. Never claim tests pass unless you ran them. Report the actual command and result.
4. List assumptions explicitly. If an assumption affects semantics (dialect, TRUNC, charset, decimal policy), ask — don't guess. Check GOAL.md section 8 for open questions first.
5. Prefer a small, complete vertical slice over a large unfinished framework.

## Hard rules
- Core (`parser`, `dsl`, `datatypes`, `mapping`, `generators`, `validation`, `reporting`) must NOT import `cli` or `mcp_server`. CLI and MCP are thin wrappers (<~15 lines per command/tool); put logic in core.
- Deterministic: same inputs ⇒ identical output. Sort keys, stable ordering, no timestamps/randomness in generated files.
- Never use an LLM or heuristics-by-guess to compute numeric ranges, scale, byte sizes or validation. Derive from the PIC/USAGE rules in `datatypes/`.
- Never silently map unsupported or lossy constructs. Emit a diagnostic with a stable code and require explicit policy or developer override.
- Source facts (DSL) are immutable. Mapping decisions live in separate override files/objects.
- Never default to floating point for decimal/packed fields.
- Treat all input as untrusted: size limits, validate archive paths (no traversal), never execute or `eval` input; run compilers/benchmarks isolated.
- Don't claim smaller types make an application faster. Label estimates vs measured results separately.
- No new runtime dependency without a one-line justification in the PR/commit. Core should stay light; MCP lives behind the `[mcp]` extra.

## Code standards
- Python 3.10+, full type hints, `mypy --strict` clean, `ruff` format + lint clean.
- Public functions have docstrings in this format:
  ```
  """One-line purpose.

  Args: name (type): meaning, units/constraints.
  Returns: type: what, including ordering guarantees.
  Raises: ErrorType: when.
  Example: a short, runnable doctest.
  """
  ```
- Small pure functions; dataclasses (`frozen=True, slots=True`) for AST/DSL nodes; custom exception hierarchy rooted at `UnboltError`.
- Version everything that changes output: DSL schema version, rule-set version, generator version.

## Documentation rules (part of "done")
- Every change updates the relevant file in `docs/` and adds a line to `CHANGELOG.md`.
- README stays a front door: one screen of install/quickstart/demo; details go in `docs/`.
- Generated docs (data-type table, supported-constructs matrix, diagnostics list, API reference) come from code/fixtures — regenerate, don't hand-edit.
- Code examples in README/docs must run in CI. If you change behavior, fix the examples.
- New public function ⇒ add it to `docs/api-reference.md` and the table in GOAL.md section 10.
- Significant design choice ⇒ add a short ADR in `docs/decisions/NNNN-title.md` (context, decision, consequences).

## Commands
No Makefile - `make` isn't reliably available cross-platform (not even
on this project's own dev machine), and these are already one command
each via `uv run`:
- `uv run pytest -q`          — full test suite (unit, golden, boundary, bench correctness)
- `uv run ruff check src tests tools` — lint
- `uv run mypy src`           — types (use `python -m mypy` if the direct binary gets blocked by local AV/AppControl policy)
- `uv run python tools/gen_performance_doc.py` — refresh docs/performance.md (not routine CI; run manually)

## Definition of done for any change
Tests added and passing (actually run) · ruff + mypy clean · docs + CHANGELOG updated · no silent lossy conversion introduced · core still independent of CLI/MCP · limitations noted honestly.

## Out of scope unless GOAL.md is updated first
Microservice decomposition, full COBOL language coverage, executing user-provided code,
Protobuf/JSON-Schema emission, any generation target beyond Go/Java/Avro-as-schema-format.
(Record decoding, variant/version modeling, and Avro + Schema-Registry integration are now in
scope — see GOAL.md §7 and phase.md Phases 8-11 — but bounded to exactly what those phases
describe.)

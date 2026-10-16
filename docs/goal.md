# GOAL.md — Unbolt

> Name: `unbolt` (PyPI: `unbolt`, import: `unbolt`, CLI: `unbolt`). The name is a pun: un-COBOL-t, releasing data definitions locked in the mainframe.
>
> One-line goal: **turn COBOL copybooks into a versioned, language-independent DSL, explain every Go/Java type choice, and generate traceable code — as a pure-Python package, a CLI, and an MCP server.**
>
> Design principle: **preserve first, explain every decision, optimize only with evidence.**

---

## 1. What we are trying to do

Mainframe data definitions (COBOL copybooks) are hard to reuse in modern services. Teams hand-translate them and lose information: numeric ranges, decimal scale, packed/binary storage, signedness, nesting, repetition, overlays (`REDEFINES`).

We build one Python package that:

1. **Parses** supported COBOL data declarations from a copybook.
2. **Converts** them to a canonical, versioned DSL (JSON-compatible) that keeps source facts immutable.
3. **Recommends** valid Go and Java types, with a written reason for every accepted and rejected candidate.
4. **Records developer decisions** (overrides) separately from source facts.
5. **Generates** deterministic Go structs and Java classes, plus validators where the type alone can't enforce the COBOL range.
6. **Validates** ranges, precision and boundaries, and **traces** every generated field back to its source line and mapping rule.
7. **Exposes** all of this through three interfaces: Python library, CLI, MCP server.

An LLM may *explain, orchestrate and summarize*. It never decides numeric ranges and never replaces the parser, mapping rules or validators.

### Who uses it
- **Developers** modernizing a mainframe data layer (library + CLI, CI pipelines).
- **AI-assisted workflows** (MCP server in Claude, Cursor, etc.): "convert this copybook and explain the type choices."
- **Reviewers/architects** who need a report showing why each type was chosen.

### Non-goals (first release)
- No automatic splitting of COBOL programs into microservices (needs program logic, not just copybooks).
- No claim that smaller types make a whole service faster.
- No claim of full COBOL coverage. Unsupported constructs are reported, never silently converted.
- No Kafka/Avro/Protobuf in the first release (see Extended scope).
- No executing uploaded content, ever.

---

## 2. The three interfaces (one core, three front doors)

| Interface | Audience | Example |
|---|---|---|
| Python library | Developers, tests, notebooks | `from unbolt import parse_copybook, build_dsl` |
| CLI | CI, scripts, no-AI users | `unbolt generate app.cpy --target go` |
| MCP server (FastMCP) | AI clients | `uvx "unbolt[mcp]" mcp` |

Rules:
- **Core never imports MCP or CLI code.** Dependency direction is always `mcp_server → core` and `cli → core`.
- MCP tools and CLI commands are thin wrappers (target: under ~15 lines each). If a wrapper grows logic, move the logic into core.
- MCP is an optional extra: `pip install "unbolt[mcp]"`. The base install stays light.
- MCP transport: stdio first (local, copybooks never leave the user's machine).

---

## 3. Architecture

```
src/unbolt/
├── parser/        # tokenizer + parser -> AST + diagnostics
├── dsl/           # versioned schema, (de)serialization, round-trip
├── datatypes/     # COBOL type model: PIC/USAGE -> range, scale, byte size
├── mapping/       # versioned rule engine -> candidates + rationale
├── overrides/     # developer decisions, stored apart from source facts
├── generators/    # go.py, java.py (+ shared templates), deterministic
├── validation/    # range/precision/boundary checks, unsupported-semantics report
├── reporting/     # mapping, validation, traceability reports (md/json)
├── performance/   # (later) storage estimates + benchmark harness
├── cli.py         # thin
└── mcp_server.py  # thin (FastMCP)
tests/  fixtures/  golden/  docs/  examples/
```

Data flow:

```
copybook text → parser → AST + diagnostics → DSL (immutable source facts)
                                              │
                    rules + overrides ────────┤→ mapping candidates + rationale
                                              │
                                              └→ generators → Go / Java + validators
                                                     └→ report (field ↔ source line ↔ rule)
```

Determinism contract: same input + DSL version + rule-set version + target + overrides ⇒ byte-identical output (stable ordering, no timestamps in generated files, no dict-order surprises).

---

## 4. Scalability and performance plan (start pure Python)

Honest starting point: a copybook is a small text file; parsing is rarely the bottleneck. The realistic scale problems are (a) repositories with thousands of copybooks, (b) `COPY ... REPLACING` resolution, (c) large generated outputs, and (d) MCP round-trip size. Plan for those, measure, then optimize.

### Stage 1 — Pure Python, built to be fast enough and easy to speed up
- **Single-pass tokenizer + recursive-descent parser.** Avoid heavy regex backtracking and repeated string slicing.
- **Immutable, slotted dataclasses** for AST/DSL nodes (`@dataclass(frozen=True, slots=True)`), small memory footprint, safe to cache and share across processes.
- **Per-file independence** so batch work parallelizes cleanly (`concurrent.futures.ProcessPoolExecutor`).
- **Content-hash cache** (hash of source + parser version + dialect) so unchanged copybooks are never re-parsed.
- **Streaming/iterators** for repo-wide runs; don't hold all ASTs in memory.
- **Lazy report generation**; MCP returns summaries plus references to full output, not megabytes of JSON.

### Stage 2 — Measure before optimizing
- Benchmark harness in `performance/` + `tests/bench/` (pytest-benchmark). Fixture sizes: 100, 1k, 10k, 100k fields; 1, 100, 5k files.
- Track: parse time, DSL build time, mapping time, generation time, peak memory (`tracemalloc`), per-stage.
- Set budgets in CI (e.g., fail on >20% regression against a stored baseline). Budgets are decided from the first measured numbers, not guessed now.
- Profile with `cProfile`/`py-spy` before changing any code.

### Stage 3 — Only if measurements justify it
Order of preference (cheapest first): algorithmic fix → caching/parallelism → `mypyc`/Cython on the hot module → Rust core via `pyo3` behind the **same Python interface**.
The **DSL JSON schema is the stable boundary**: any faster parser (Rust or otherwise) must produce identical DSL for every golden fixture. That makes a later swap low-risk.

### Rule for performance claims
Reports label **estimated** (theoretical storage by type, stated assumptions) separately from **measured** (benchmarked, with environment/workload recorded). Never mix them.

---

## 5. COBOL data types, ranges and sizes (reference we must document and test)

This table is the seed for `docs/cobol-datatypes.md`. **Ranges must come from code (`datatypes/`), and the doc table should be generated from that code** so docs can't drift.

### 5.1 Numeric — DISPLAY (zoned decimal)
| Picture | Meaning | Range | Bytes |
|---|---|---|---|
| `PIC 9(n)` | unsigned, n digits | `0 … 10ⁿ−1` (e.g., `9(3)` → 0…999) | n |
| `PIC S9(n)` | signed, n digits | `−(10ⁿ−1) … +(10ⁿ−1)` | n (sign "overpunched" in last digit's zone) |
| `PIC S9(n) SIGN IS SEPARATE` | explicit `+`/`-` char | same as above | n + 1 |
| `PIC 9(n)V9(m)` | implied decimal point | scale m; value = integer / 10ᵐ; total digits n+m | n+m (the `V` takes no storage) |

Notes: overpunch encoding depends on character set (EBCDIC vs ASCII). The dialect/codepage must be an explicit parser/generator setting.

### 5.2 Packed decimal — `COMP-3` / `PACKED-DECIMAL`
- Two digits per byte; the last nibble is the sign (`C`/`F` positive, `D` negative; `F` for unsigned).
- Bytes = `floor(digits / 2) + 1`.
- Digits: up to 31 on IBM Enterprise COBOL (older/other compilers may cap lower — document per dialect).
- Example: `PIC S9(9)V99 COMP-3` → 11 digits, scale 2, 6 bytes, range ±999,999,999.99. **Map to exact decimal, never float, unless an explicit reviewed policy says otherwise.**

### 5.3 Binary — `COMP` / `COMP-4` / `BINARY`
| Digits in PIC | Storage | Bytes |
|---|---|---|
| 1–4 | halfword | 2 |
| 5–9 | fullword | 4 |
| 10–18 | doubleword | 8 |

- Big-endian on mainframe. Full binary ranges: 2 bytes −32,768…32,767 (unsigned 0…65,535); 4 bytes −2³¹…2³¹−1 (unsigned up to 2³²−1); 8 bytes −2⁶³…2⁶³−1 (unsigned up to 2⁶⁴−1).
- **The usable range depends on the compiler's truncation option.** `TRUNC(STD)`: values are limited to the PIC digits (`PIC 9(4) COMP` ⇒ max 9999). `TRUNC(BIN)`: full binary range. `TRUNC(OPT)`: behavior beyond the PIC range isn't guaranteed. Make this an explicit setting; default to the safest (PIC-limited) range and document it.

### 5.4 Floating point — `COMP-1` / `COMP-2`
- 4-byte and 8-byte floats. On IBM mainframes the default is **hexadecimal floating point (HFP), not IEEE 754**. Flag as "supported with caveats / needs explicit policy"; never auto-map silently.

### 5.5 Character and national
| Picture | Meaning | Bytes |
|---|---|---|
| `PIC X(n)` | alphanumeric | n (EBCDIC or ASCII per dialect) |
| `PIC A(n)` | alphabetic | n |
| `PIC N(n)` / `PIC G(n)` | national / DBCS | 2 per character |

### 5.6 Structure and special constructs
| Construct | Meaning | First-release stance |
|---|---|---|
| Level `01`–`49` | hierarchy (groups vs elementary items) | Supported |
| `OCCURS n` | fixed repetition | Supported |
| `OCCURS … DEPENDING ON` | variable-length table | Detect + report; model later |
| `REDEFINES` | overlay of the same bytes | Supported as union/overlay metadata; mapping needs explicit policy |
| Level `66` (`RENAMES`) | alias over a range of items | Diagnostic (unsupported) |
| Level `77` | standalone item | Supported |
| Level `88` | condition names (values, not storage) | Preserve as metadata/enums; no storage |
| `SYNCHRONIZED` | alignment padding | Detect + report; affects offsets |
| `JUSTIFIED`, `BLANK WHEN ZERO` | display behavior | Preserve as metadata |
| Edited pictures (`Z`, `*`, `$`, `,`, `.`, `+`, `-`, `CR`, `DB`) | display formatting only | Treat as text; diagnostic |
| `COPY … REPLACING` | text inclusion/substitution | Phase-later; report if unresolved |
| `VALUE` | initial value | Preserve as metadata |

### 5.7 Mapping examples the rule engine must get right (and test at the boundaries)
| Source range | Go candidates | Java candidates | Rejections (with reason) |
|---|---|---|---|
| `PIC 9(3)` (0…999) | `uint16`, `int` | `short`, `int` | Go `uint8` rejected (max 255 < 999). Validator still needed to enforce ≤ 999. |
| `PIC S9(4)` (±9999) | `int16`, `int32`, `int` | `short`, `int` | `int8`/`byte` too small |
| `PIC S9(9)` (±999,999,999) | `int32`, `int64` | `int`, `long` | `int16`/`short` too small |
| `PIC S9(18)` | `int64` | `long` | 32-bit types too small |
| `PIC S9(19+)` | `big.Int` or decimal string | `BigInteger` | `int64`/`long` can't hold all values |
| `PIC S9(9)V99 COMP-3` | exact decimal (e.g., a decimal lib, or scaled `int64` by policy) | `BigDecimal` | `float32/64`, `float/double` rejected by default |

Reminder: Java has no unsigned primitives, so unsigned source fields map to the next larger signed type, plus a range validator where needed. A wider type never enforces the COBOL maximum by itself.

---

## 6. Scope: phases with exit criteria

| Phase | Deliverable | Exit criteria |
|---|---|---|
| 0 | Supported-constructs list, sample copybooks, DSL v0 schema, acceptance criteria | Reviewed and written down |
| 1 | Parser + DSL | Parser tests pass; DSL deterministic and round-trippable; diagnostics for unsupported syntax |
| 2 | Mapping engine (Go, Java) with explanations | Tests cover valid, invalid, ambiguous cases; overrides stored separately |
| 3 | Go and Java code generation | Golden-file tests pass; generated examples compile where toolchains exist |
| 4 | Validation, boundary tests, traceability, conversion report | Every generated field traces to source line, DSL node, rule |
| 5 | **CLI** and **MCP server** | MCP client runs the full workflow with no duplicated core logic; CLI covers the same operations |
| 6 | Storage estimates, then benchmarks | Estimates and measurements clearly separated; environment recorded |
| 7 | Hardening, docs, CI, demo | New developer runs the demo from the README and reproduces tests |

Publish an early `0.x` to PyPI after Phase 3–4 (library + CLI) so there is something real to try before MCP.

### MVP done when
- A sample copybook parses into a versioned DSL with source metadata.
- Unsupported constructs produce clear diagnostics (stable codes), not silent lossy conversion.
- The mapping engine explains Go and Java candidates and rejects invalid ranges.
- Approved mappings generate deterministic Go and Java.
- Tests cover representative fields and numeric boundaries.
- Generated examples compile where toolchains are present.
- Every output field is traceable to its source declaration and rule.
- Docs state assumptions, supported syntax, limitations, and how to reproduce the demo.

---

## 7. Extended scope (later, only after the core is reliable)

Each item needs its own short design note in `docs/decisions/` before work starts.

- **Record decoders:** generate code that reads actual fixed-width EBCDIC/ASCII records (zoned, packed, binary) into the generated structs. This is where most real modernization value lives.
- **More targets:** Python dataclasses/Pydantic, TypeScript, Rust, Kotlin, C#.
- **Schema formats:** JSON Schema, Protobuf, Avro (currently out of scope).
- **Repo-wide analysis:** copybook dependency graph, `COPY` resolution, duplicate/near-duplicate record detection.
- **Test-data generation:** boundary and random records from the DSL; round-trip checks against sample mainframe data files.
- **Compilation orchestration** and **benchmark tools** exposed over MCP (isolated sandbox).
- **LLM-assisted explanations** (summaries of a report, migration notes) — strictly downstream of deterministic output.
- **Editor/UI:** web viewer for the traceability report; VS Code extension.
- **Performance core in Rust (`pyo3`)** if Stage 3 measurements justify it.

---

## 8. Questions to settle (ask before/while building)

Answer these early; record answers as decisions in `docs/decisions/`.

1. Which COBOL dialects first: IBM Enterprise COBOL, Micro Focus, GnuCOBOL? (Affects digit limits, floats, `TRUNC`.)
2. Character set: EBCDIC, ASCII, or both? Which code page(s)?
3. Default `TRUNC` behavior to assume when the user doesn't specify?
4. Go decimal policy: external decimal library vs scaled `int64` vs string? Who decides, the tool or a config default?
5. Java style: POJO, record, Lombok, or configurable?
6. Naming: `ACCOUNT-AGE` → `AccountAge` / `accountAge`; collision handling; reserved words in Go/Java.
7. `REDEFINES`: union-like generated types, separate structs, or require explicit developer choice?
8. Should the first public release include record decoding, or only type/model generation?
9. What does "approved" mean: a config file, a CLI flow, an MCP tool call, or all three?
10. Minimum Python version (suggest 3.10+, required by FastMCP) and license (Apache-2.0 or MIT).

---

## 9. Documentation plan

All docs are Markdown in the repo, written for people **and** readable by AI assistants.

```
README.md                  # front door (see 9.1)
GOAL.md                    # this file: why and what
CLAUDE.md                  # instructions for Claude Code (see section 11)
CHANGELOG.md               # Keep a Changelog format
CONTRIBUTING.md
docs/
├── index.md               # map of all docs
├── concepts.md            # copybook → AST → DSL → mapping → code, in plain words
├── cobol-datatypes.md     # section 5, generated from datatypes/ where possible
├── supported-constructs.md# matrix: Supported / Partial / Diagnostic / Unsupported
├── dsl-spec.md            # versioned schema, field-by-field, with examples
├── mapping-rules.md       # every rule: id, version, condition, outcome, rationale
├── diagnostics.md         # every diagnostic code, meaning, how to fix
├── cli.md                 # every command and flag, with output samples
├── mcp.md                 # every tool: params, returns, errors, client config snippets
├── architecture.md        # modules and the dependency rule
├── api-reference.md       # public functions (see section 10); generated from docstrings
├── performance.md         # methods, budgets, latest measured results vs estimates
├── limitations.md         # honest list of what doesn't work
└── decisions/             # short ADRs: 0001-dsl-format.md, ...
```

### 9.1 How to write the README (and keep it good)

Structure, in this order:
1. **Name + one-sentence description** (what, for whom).
2. **Why**: the lossy-translation problem in 3–4 lines.
3. **30-second demo**: a copybook snippet → generated Go/Java + one line of the "why this type" explanation. Real output, not mock.
4. **Install**: `pip install`, `pip install "…[mcp]"`, `uvx` one-liner.
5. **Quickstart ×3**: library, CLI, MCP (with the client JSON config).
6. **Supported / not supported** (short table + link to `supported-constructs.md`).
7. **How it works**: 5-line pipeline diagram + link to `docs/concepts.md`.
8. **Docs index**, **Limitations**, **Contributing**, **License**.

Keep it clean over time:
- **README is a front door, not the manual.** Anything longer than a screen goes to `docs/` and the README links to it.
- **Docs as tests:** README and docs code blocks run in CI (`pytest --doctest-glob="*.md"` or a small script). A broken example fails the build.
- **Generate, don't hand-write, what can drift:** the data-type range table, the supported-constructs matrix, the diagnostics list and the API reference come from code/fixtures/docstrings (`mkdocs` + `mkdocstrings`, or a small generator script).
- **Docs change in the same PR as the code.** Definition of done includes docs and a CHANGELOG line.
- **CI checks:** markdown lint, link check, docs build.
- **One fact, one place.** Link instead of copy.
- **Plain language first, then precision.** Each page starts with "what this is for" and a runnable example.
- **Date or version-stamp** anything that can go stale (compiler behavior, benchmark numbers).

---

## 10. Public API: what each major method must do

Each function is pure where possible (no hidden I/O or global state), typed, and has the docstring format in section 11. This table is the contract; update it when code changes.

| Function | Module | Does | Returns | Fails with |
|---|---|---|---|---|
| `parse_copybook(source, *, dialect, charset)` | `parser` | Tokenize and parse supported declarations. Never executes input. Applies size limits. | `ParseResult` (AST + diagnostics + source locations) | `InputTooLargeError`, `InvalidInputError`; unsupported syntax becomes **diagnostics**, not exceptions |
| `build_dsl(parse_result, *, version)` | `dsl` | Convert AST to canonical DSL: hierarchy, PIC, usage, sign, precision, scale, OCCURS, REDEFINES, locations. Source facts only. | `Dsl` (JSON-serializable, versioned) | `DslBuildError` if parse had blocking errors |
| `Dsl.to_json()` / `Dsl.from_json()` | `dsl` | Stable, sorted, round-trippable serialization | `str` / `Dsl` | `SchemaVersionError` |
| `describe_datatype(field)` | `datatypes` | Compute min/max, digits, scale, signedness, byte size for a field under a chosen `TRUNC`/dialect | `TypeFacts` | `UnsupportedPictureError` |
| `recommend_mappings(dsl, target, *, rules, overrides)` | `mapping` | Evaluate each field against versioned rules; return every candidate with status (valid/invalid/needs-policy), rationale, constraints, trade-offs. Never invents ranges. | `MappingReport` | `UnknownTargetError` |
| `apply_override(overrides, field_path, choice, reason)` | `overrides` | Record a developer decision; source facts untouched | new `Overrides` | `InvalidChoiceError` (choice not among valid candidates unless force-flagged) |
| `generate_code(dsl, mapping, target, *, options)` | `generators` | Emit deterministic Go or Java from approved mappings; add validators where the type can't enforce the range | `GeneratedFiles` (path → content) | `UnapprovedMappingError` if any field is unresolved |
| `validate_conversion(dsl, mapping, generated)` | `validation` | Boundary checks (min, max, min−1, max+1), precision/scale checks, unsupported-semantics list; optional compile check if toolchain exists | `ValidationReport` | — (findings are data) |
| `build_report(dsl, mapping, validation)` | `reporting` | Field ↔ source line ↔ DSL node ↔ rule ↔ rationale trace, warnings, unsupported constructs | `ConversionReport` (md + json) | — |
| `estimate_storage(dsl, mapping)` *(Phase 6)* | `performance` | Theoretical size per record with stated assumptions | `Estimate` (labeled "estimated") | — |
| `run_benchmarks(config)` *(Phase 6)* | `performance` | Controlled, reproducible runs; records environment | `BenchmarkResult` (labeled "measured") | — |

MCP tools map 1:1 to these: `parse_copybook`, `generate_dsl`, `recommend_type_mapping`, `update_mapping_override`, `generate_target_code`, `validate_conversion`, `generate_conversion_report`. Each tool: validate input → call one core function → return structured result (small, with references for large payloads).

CLI commands mirror them: `parse`, `dsl`, `recommend`, `override`, `generate`, `validate`, `report`, and `mcp` (starts the server).

**Diagnostics:** stable codes, e.g., `CBL-E001` (error) / `CBL-W010` (warning) / `CBL-I100` (info), each with a message, source location and a docs anchor in `docs/diagnostics.md`.

---

## 11. Claude Code instructions (copy this section to `CLAUDE.md`)

```markdown
# CLAUDE.md — Unbolt

Read GOAL.md first. It is the source of truth for scope, architecture and phases.

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

## Commands (create a Makefile / task runner with these)
- `make test`   — pytest (unit, golden, boundary)
- `make lint`   — ruff + mypy
- `make docs`   — build docs, run doc examples, check links
- `make bench`  — benchmarks (Phase 6+)
- `make check`  — lint + test + docs; must pass before saying a phase is done

## Definition of done for any change
Tests added and passing (actually run) · `make check` green · docs + CHANGELOG updated · no silent lossy conversion introduced · core still independent of CLI/MCP · limitations noted honestly.

## Out of scope unless GOAL.md is updated first
Microservice decomposition, Kafka/Avro, full COBOL language coverage, executing user-provided code.
```

---

## 12. Risks (and what we do about them)

| Risk | Mitigation |
|---|---|
| COBOL semantic loss | Model supported constructs explicitly; fail safely with diagnostics |
| Wrong target type | Range/precision rules, boundary tests, explicit overrides |
| Dialect differences (digit limits, floats, TRUNC) | Make dialect/TRUNC explicit settings; document per dialect |
| False performance claims | Estimates and measurements always labeled and separated |
| Scope creep | Phase exit criteria; extended scope needs a design note first |
| Unsafe input / execution | Size limits, path validation, never execute input, isolated builds |
| Docs drift | Generate from code, run examples in CI, docs required in definition of done |
| Existing tools (Cobrix, cb2xml, JRecord, etc.) | Differentiate on explainable type mapping, traceability, and the MCP workflow; say this plainly in the README |

---

## 13. Open source checklist

- License file (Apache-2.0 or MIT), `CONTRIBUTING.md`, issue templates, "good first issue" labels (each new COBOL construct is a small, well-scoped contribution).
- GitHub Actions: lint, type-check, tests, doc-example tests, Go/Java compile checks on generated output.
- PyPI release via trusted publishing (no API tokens); upload a `0.0.1` placeholder early to hold the package name.
- List the MCP server in the MCP registry and awesome-mcp lists once Phase 5 works.
- Keep a public roadmap (this file's section 6–7) and update it as phases complete.
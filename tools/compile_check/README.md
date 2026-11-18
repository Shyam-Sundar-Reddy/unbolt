# Compile-check

Generates Go and Java for every `fixtures/*.cpy` and compiles
them with real toolchains via Docker (`golang:1.23`, `eclipse-temurin:21-jdk`).
Dev-only, not wired into CI (phase.md step 8 calls this "optional").

Also generates the Go flyweight decoder (ADR 0009, Phase 10) for
`flat_display.cpy` — the one fixture inside its current slice's scope
(flat, `DISPLAY`-only records) — and actually **runs** it against real
hand-crafted bytes, asserting the decoded values match exactly what
Python's own `decode_record()` already verified (ADR 0009: round-trip
tests are part of Phase 10's acceptance criteria, not optional).

Caught three real bugs that string-matching unit tests missed: nested
Java classes rendered outside their parent's braces, validator methods
floating outside any class, and missing `fmt`/`math/big` Go imports.

## Run it

```bash
uv run python tools/compile_check/check.py
```

Skips gracefully (exit 0) if Docker isn't available.

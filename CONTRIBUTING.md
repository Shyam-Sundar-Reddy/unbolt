# Contributing to unbolt

## Setup

```bash
git clone https://github.com/Shyam-Sundar-Reddy/unbolt.git
cd unbolt
uv sync --extra dev
```

## Before sending a change

```bash
uv run pytest -q                            # full test suite
uv run ruff check src tests tools           # lint
uv run mypy src                             # types (strict)
```

All three must be clean. If `mypy` gets blocked by local antivirus/
Application Control policy (`Failed to spawn: mypy`), run
`uv run python -m mypy src` instead — same tool, different invocation
path.

## Adding a new COBOL construct

Each new construct (another `PICTURE` symbol, a `USAGE` variant, a
clause) is a well-scoped, independent contribution:

1. Add a fixture under `fixtures/` demonstrating it, or extend an
   existing one.
2. Hand-compute the expected byte size/range and cross-check it against
   [docs/acceptance-criteria.md](docs/acceptance-criteria.md)'s
   approach (and, if you have Docker, `tools/gnucobol_check/` — an
   independent compiler's opinion on your math is worth more than
   another unit test agreeing with itself).
3. Add the parsing/sizing logic and a test per construct, following
   the existing style in `tests/test_parser_constructs.py`.
4. Update [docs/supported-constructs.md](docs/supported-constructs.md)
   — it should never drift from what the parser actually does.

## Hard rules (see `CLAUDE.md` for the full list)

- Never silently convert something unsupported — emit a diagnostic
  with a stable code instead.
- Never default a decimal/packed field to `float`/`double`.
- Core (`parser`, `dsl`, `datatypes`, `mapping`, `generators`,
  `validation`, `reporting`, `performance`) never imports `cli` or
  `mcp_server`.
- Label performance numbers `estimated` or `measured` — never both,
  never mixed.
- An assumption about COBOL semantics (dialect, charset, TRUNC,
  decimal policy) needs an explicit decision, not a guess — see
  `docs/decisions/` for the pattern (new ones are local-only for now,
  same as `docs/phase.md`).

## Running the dev-only verification tools

Neither is part of CI; both need Docker:

```bash
docker build -t unbolt-gnucobol-check tools/gnucobol_check
uv run python tools/gnucobol_check/check.py   # cross-checks byte sizes against a real compiler

uv run python tools/compile_check/check.py    # compiles generated Go/Java with real toolchains
```

## License

Apache-2.0 (see [LICENSE](LICENSE)). By contributing, you agree your
contribution is licensed under the same terms.

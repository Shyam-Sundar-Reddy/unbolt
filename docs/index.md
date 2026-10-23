# Docs index

## For users

- [../README.md](../README.md) — install, quickstart, 30-second demo
- [cli.md](cli.md) — every CLI command and flag, with real output
- [mcp.md](mcp.md) — every MCP tool: params, returns, errors, client config
- [supported-constructs.md](supported-constructs.md) — what's parsed, diagnosed, or unsupported
- [limitations.md](limitations.md) — honest list of what doesn't work yet
- [../CONTRIBUTING.md](../CONTRIBUTING.md) — setup, hard rules, adding a construct

## Reference, generated from code (regenerate, don't hand-edit)

- [dsl-spec.md](dsl-spec.md) — the DSL schema, field by field
- [mapping-rules.md](mapping-rules.md) — every Go/Java mapping rule, from `tools/gen_mapping_rules_doc.py`
- [diagnostics.md](diagnostics.md) — every diagnostic code, from `tools/gen_diagnostics_doc.py`
- [performance.md](performance.md) — estimated vs. measured, from `tools/gen_performance_doc.py` (run manually, not routine CI)

## Internal (not tracked — local only)

These exist on disk for anyone working in this clone, but aren't
pushed: `goal.md`, `phase.md`, `agents.md`, `acceptance-criteria.md`,
`decisions/*.md`. Planning and verification scaffolding, not
end-user reference material.

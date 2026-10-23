# CLI

`unbolt` (stdlib `argparse` — see decision discussion in `docs/phase.md`
Phase 5: no new runtime dependency justified for a handful of
subcommands with simple flags). Seven commands, each a thin wrapper
over exactly one core function (`src/unbolt/cli.py`).

## `unbolt parse <file>`

Parses a copybook and prints its diagnostics (or `no diagnostics`).

```
$ unbolt parse fixtures/flat_display.cpy
no diagnostics
```

## `unbolt dsl <file>`

Prints the versioned DSL as JSON (`Dsl.to_json()`).

```
$ unbolt dsl fixtures/flat_display.cpy
{
  "roots": [
    {
      "byte_size": 18,
      ...
```

## `unbolt recommend <file> --target go|java`

Prints every candidate for every field, not just the winner.

```
$ unbolt recommend fixtures/flat_display.cpy --target go
CUSTOMER-RECORD.CUSTOMER-ID
  invalid      int8                 int8 holds -128..127, too small for the field's 0..999999
  ...
  valid        int32                int32 holds -2147483648..2147483647, which covers the field's 0..999999
  ...
```

## `unbolt override <file> <field_path> <type> --target go|java --reason "..." [--force] [--overrides-file path]`

Records a developer's type choice (decision 0007: a JSON file,
`.unbolt-overrides.json` by default). Rejects a choice outside the
field's own candidates unless `--force`.

```
$ unbolt override fixtures/mixed_usage.cpy FINANCIAL-RECORD.SENSOR-READING float32 \
    --target go --reason "best-effort IEEE754 approximation" --force
saved: FINANCIAL-RECORD.SENSOR-READING -> float32
```

## `unbolt generate <file> --target go|java -o <dir> [--overrides-file path]`

Writes generated files under `<dir>`.

```
$ unbolt generate fixtures/flat_display.cpy --target go -o out/
wrote out/gen.go
```

## `unbolt validate <file> --target go|java [--overrides-file path]`

Prints validation findings (or `no findings`).

```
$ unbolt validate fixtures/flat_display.cpy --target go
no findings
```

## `unbolt report <file> --target go|java [--format md|json] [--overrides-file path]`

Prints the full conversion report (field, source line, chosen type,
rule, rationale) plus any findings.

```
$ unbolt report fixtures/flat_display.cpy --target go
# Conversion report (go)

## Fields

| Field | Source line | Chosen type | Rule | Rationale |
|---|---|---|---|---|
| `CUSTOMER-RECORD.ACCOUNT-BALANCE` | 5 | `int64 (scaled)` | `go-decimal-int64-scaled` | ... |
```

## `unbolt mcp`

Starts the MCP server over stdio (`src/unbolt/mcp_server.py`, see
`docs/mcp.md`). Lazily imports `fastmcp`, so the base `unbolt` install
doesn't need the `[mcp]` extra unless you actually run this command.

```
$ unbolt mcp
# blocks, serving MCP tool calls over stdio
```

## Notes

- `--overrides-file` defaults to `.unbolt-overrides.json` in the
  current directory on every command that touches overrides
  (`override`, `generate`, `validate`, `report`). A missing file means
  no overrides, not an error.
- An override file is implicitly scoped to the `--target` you ran
  `override` with — type names are target-specific (`int16` vs
  `short`). Use separate `--overrides-file` paths if you need
  different choices for Go and Java on the same copybook.

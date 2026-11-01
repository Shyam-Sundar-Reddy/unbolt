# MCP server

`unbolt mcp` (`src/unbolt/mcp_server.py`, FastMCP, stdio transport
only — goal.md section 2: copybooks never leave the user's machine).
Behind the `[mcp]` extra: `pip install "unbolt[mcp]"`.

All 8 tools take a local path to a copybook (`file_path`, or
`old_file`/`new_file` for `check_compatibility`) rather than inline
source text or a reference to a previous tool's result — each call
re-parses from disk. Parsing is cheap (goal.md section 4: "a copybook
is a small text file"), and this avoids needing any cross-call
session state.

## `parse_copybook(file_path: str)`

- **Returns:** `{"diagnostics": [{"code", "severity", "message", "line"}, ...], "roots": [field names]}`
- **Errors:** file not found; `InvalidInputError` (empty/invalid source).

## `generate_dsl(file_path: str)`

- **Returns:** the full `Dsl` as JSON (same shape as `Dsl.to_json()`).
- **Errors:** same as `parse_copybook`.

## `recommend_type_mapping(file_path: str, target: str)`

- **Returns:** the full `MappingReport` as JSON — every candidate for
  every field, with `status`/`rule_id`/`rationale`, not just the winner.
- **Errors:** `UnknownTargetError` if `target` isn't `"go"`/`"java"`.

## `update_mapping_override(file_path, target, field_path, choice, reason, force=False, overrides_file=".unbolt-overrides.json")`

- **Returns:** `{"field_path": ..., "choice": ...}`.
- **Errors:** `InvalidChoiceError` if `choice` isn't among the field's
  own candidates and `force` is false.
- Writes to the same JSON file decision 0007 defines for the CLI's
  `unbolt override` — point both at the same file to share state.

## `generate_target_code(file_path, target, overrides_file=".unbolt-overrides.json")`

- **Returns:** `{"relative_path": "file content"}` — one entry for Go,
  one per class for Java.
- **Errors:** `UnapprovedMappingError` if any field has no override
  and no valid candidate.

## `validate_conversion(file_path, target, overrides_file=".unbolt-overrides.json")`

- **Returns:** the full `ValidationReport` as JSON — a `findings` list,
  each `{"field_path", "code", "severity", "message"}`.
- **Errors:** same as `generate_target_code` (it generates code
  internally to check completeness against).

## `generate_conversion_report(file_path, target, format="markdown", overrides_file=".unbolt-overrides.json")`

- **Returns:** the rendered report as a string (`format="json"` for
  the JSON form instead).
- **Errors:** same as `generate_target_code`.

## `check_compatibility(old_file, new_file, mode=None)`

Classifies how `new_file`'s record layout differs from `old_file`'s:
`FULL`, `FORWARD`, `BACKWARD`, or `BREAKING` (decision 0011). The
rules are asymmetric because COBOL records are positional, not
tagged: a field added purely at the end is `FORWARD`-compatible only
(an old reader never looks at the new trailing bytes); a field
removed purely from the end is `BACKWARD`-compatible only. Reordering,
a middle insert/removal, or any change to a shared field's offset/
size/type/scale is always `BREAKING`.

- **Returns:** the `CompatibilityResult` as JSON — `compatibility`
  plus a `changes` list, each `{"field_path", "kind", "detail"}`
  (`kind` is `"added"`, `"removed"`, or `"changed"`).
- **Errors:** if `mode` (`"backward"`/`"forward"`/`"full"`) is given
  and the verdict doesn't satisfy it, raises `IncompatibleChangeError`
  instead of returning quietly.

```json
{
  "compatibility": "FORWARD",
  "changes": [
    {
      "field_path": "CUSTOMER-RECORD.CUSTOMER-EMAIL",
      "kind": "added",
      "detail": "added at offset 9, 40 bytes"
    }
  ]
}
```

This is a structural judgment on the two DSL shapes — it doesn't mean
`generate_target_code`/decoding would tolerate the length difference;
record decoding (`unbolt.decoding`) still requires an exact length
match (decision 0010).

## Client config

```json
{
  "mcpServers": {
    "unbolt": {
      "command": "uvx",
      "args": ["unbolt[mcp]", "mcp"]
    }
  }
}
```

# MCP server

`unbolt mcp` (`src/unbolt/mcp_server.py`, FastMCP, stdio transport
only — goal.md section 2: copybooks never leave the user's machine).
Behind the `[mcp]` extra: `pip install "unbolt[mcp]"`.

All 7 tools take a `file_path` (local path to a copybook) rather than
inline source text or a reference to a previous tool's result — each
call re-parses from disk. Parsing is cheap (goal.md section 4: "a
copybook is a small text file"), and this avoids needing any
cross-call session state.

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

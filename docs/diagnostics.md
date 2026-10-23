# Diagnostics

Generated from `DIAGNOSTIC_CATALOG` in `src/unbolt/parser/diagnostics.py` by `tools/gen_diagnostics_doc.py` - regenerate, don't hand-edit. Every diagnostic has a stable code; unsupported syntax produces one of these instead of a crash or a silent skip.

| Code | Severity | Meaning | How to fix |
|---|---|---|---|
| `CBL-E001` | error | A data-description entry's level number couldn't be parsed, or the entry has no name after its level number. | Check the level number and field name on the reported line. |
| `CBL-W010` | warning | COPY ... REPLACING is recognized but not supported; the entry is skipped. | Expand the COPY member by hand, or wait for COPY REPLACING support (goal.md Extended scope). |
| `CBL-W020` | warning | Level 66 (RENAMES) is recognized but not supported; the entry is skipped. | Remove the RENAMES entry, or reference the renamed range directly. |
| `CBL-W030` | warning | OCCURS ... DEPENDING ON is recognized but not supported; the field is treated as not a table (occurs=None). | Use a fixed OCCURS n instead, or model the maximum size explicitly. |
| `CBL-W040` | warning | A clause token wasn't recognized and was skipped. | Check the clause's spelling/syntax against docs/supported-constructs.md. |
| `CBL-I100` | info | SYNCHRONIZED was detected; alignment padding is not modeled. | No action needed unless exact byte offsets matter for a future record decoder. |
| `CBL-I101` | info | JUSTIFIED was detected; noted but not stored on FieldNode - no behavioral or sizing effect. | No action needed. |
| `CBL-I102` | info | A generated Java field name collided with a reserved word and was renamed with a trailing '_' (decision 0003). | No action needed; the renamed identifier is still traceable via this diagnostic. |
| `CBL-I103` | info | BLANK WHEN ZERO was detected; not stored, no behavioral effect. | No action needed. |
| `CBL-W050` | warning | An edited picture (Z, *, $, comma, decimal point, +/-, CR/DB) was detected; sized as text width, excluded from numeric mapping. | If you need the real numeric value, use the unedited source field if one exists, or treat this field as display-only text. |

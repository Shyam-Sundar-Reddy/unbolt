"""Regenerate docs/diagnostics.md from DIAGNOSTIC_CATALOG.

Run after adding/changing a diagnostic in src/unbolt/parser/diagnostics.py
- don't hand-edit the generated file.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from unbolt.parser.diagnostics import DIAGNOSTIC_CATALOG  # noqa: E402


def main() -> None:
    lines = [
        "# Diagnostics",
        "",
        "Generated from `DIAGNOSTIC_CATALOG` in "
        "`src/unbolt/parser/diagnostics.py` by `tools/gen_diagnostics_doc.py` - "
        "regenerate, don't hand-edit. Every diagnostic has a stable code; "
        "unsupported syntax produces one of these instead of a crash or a "
        "silent skip.",
        "",
        "| Code | Severity | Meaning | How to fix |",
        "|---|---|---|---|",
    ]
    for code, severity, meaning, fix in DIAGNOSTIC_CATALOG:
        lines.append(f"| `{code}` | {severity} | {meaning} | {fix} |")

    out_path = ROOT / "docs" / "diagnostics.md"
    out_path.write_text("\n".join(lines) + "\n")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()

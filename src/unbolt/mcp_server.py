"""MCP tools, 1:1 with goal.md section 10's core functions. Each tool is
a thin wrapper - stdio transport only, so copybooks never leave the
user's machine (goal.md section 2). Behind the [mcp] extra; importing
this module without it installed fails at the fastmcp import, not
silently.
"""

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from unbolt.dsl import Dsl, build_dsl
from unbolt.generators import generate_code
from unbolt.mapping import recommend_mappings, valid_candidate_names
from unbolt.overrides import apply_override, load_overrides, save_overrides
from unbolt.overrides.persistence import DEFAULT_OVERRIDES_PATH
from unbolt.parser import parse_copybook
from unbolt.reporting import build_report, render_json, render_markdown
from unbolt.validation import validate_conversion as _validate_conversion

mcp = FastMCP("unbolt")


def _file_to_dsl(file_path: str) -> Dsl:
    source = Path(file_path).read_text()
    return build_dsl(parse_copybook(source), source_file=file_path)


@mcp.tool(name="parse_copybook")
def parse_copybook_tool(file_path: str) -> dict[str, Any]:
    """Parse a COBOL copybook; return its diagnostics and root field names."""
    result = parse_copybook(Path(file_path).read_text())
    return {
        "diagnostics": [asdict(d) for d in result.diagnostics],
        "roots": [r.name for r in result.roots],
    }


@mcp.tool
def generate_dsl(file_path: str) -> dict[str, Any]:
    """Parse a copybook and return its versioned DSL as JSON."""
    return asdict(_file_to_dsl(file_path))


@mcp.tool
def recommend_type_mapping(file_path: str, target: str) -> dict[str, Any]:
    """Every Go/Java type candidate for every field, with status and rationale."""
    return asdict(recommend_mappings(_file_to_dsl(file_path), target))


@mcp.tool
def update_mapping_override(
    file_path: str,
    target: str,
    field_path: str,
    choice: str,
    reason: str,
    force: bool = False,
    overrides_file: str = DEFAULT_OVERRIDES_PATH,
) -> dict[str, Any]:
    """Record a developer's type choice for one field (decision 0007: JSON file)."""
    report = recommend_mappings(_file_to_dsl(file_path), target)
    overrides = load_overrides(overrides_file)
    overrides = apply_override(
        overrides, field_path, choice, reason,
        valid_choices=valid_candidate_names(report, field_path), force=force,
    )
    save_overrides(overrides, overrides_file)
    return {"field_path": field_path, "choice": choice}


@mcp.tool
def generate_target_code(
    file_path: str, target: str, overrides_file: str = DEFAULT_OVERRIDES_PATH
) -> dict[str, str]:
    """Generate Go or Java source for a copybook; returns {path: content}."""
    dsl = _file_to_dsl(file_path)
    report = recommend_mappings(dsl, target)
    overrides = load_overrides(overrides_file)
    return generate_code(dsl, report, target, overrides=overrides)


@mcp.tool
def validate_conversion(
    file_path: str, target: str, overrides_file: str = DEFAULT_OVERRIDES_PATH
) -> dict[str, Any]:
    """Boundary/precision/completeness findings for a copybook's conversion."""
    dsl = _file_to_dsl(file_path)
    report = recommend_mappings(dsl, target)
    overrides = load_overrides(overrides_file)
    generated = generate_code(dsl, report, target, overrides=overrides)
    return asdict(_validate_conversion(dsl, report, generated))


@mcp.tool
def generate_conversion_report(
    file_path: str,
    target: str,
    format: str = "markdown",
    overrides_file: str = DEFAULT_OVERRIDES_PATH,
) -> str:
    """Field <-> source line <-> rule <-> rationale trace, as markdown or JSON."""
    dsl = _file_to_dsl(file_path)
    mapping = recommend_mappings(dsl, target)
    overrides = load_overrides(overrides_file)
    generated = generate_code(dsl, mapping, target, overrides=overrides)
    validation = _validate_conversion(dsl, mapping, generated)
    report = build_report(dsl, mapping, validation, overrides=overrides)
    return render_json(report) if format == "json" else render_markdown(report)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

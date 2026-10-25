import asyncio
from pathlib import Path

import pytest
from fastmcp import Client

from unbolt.mcp_server import mcp

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
FLAT = str(FIXTURES_DIR / "flat_display.cpy")
MIXED = str(FIXTURES_DIR / "mixed_usage.cpy")


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def test_server_lists_all_seven_tools_matching_goal_md() -> None:
    async def go():  # type: ignore[no-untyped-def]
        async with Client(mcp) as client:
            return [t.name for t in await client.list_tools()]

    names = _run(go())
    assert set(names) == {
        "parse_copybook",
        "generate_dsl",
        "recommend_type_mapping",
        "update_mapping_override",
        "generate_target_code",
        "validate_conversion",
        "generate_conversion_report",
    }


def test_parse_copybook_tool() -> None:
    async def go():  # type: ignore[no-untyped-def]
        async with Client(mcp) as client:
            return await client.call_tool("parse_copybook", {"file_path": FLAT})

    result = _run(go())
    assert result.data == {"diagnostics": [], "roots": ["CUSTOMER-RECORD"]}


def test_generate_dsl_tool() -> None:
    async def go():  # type: ignore[no-untyped-def]
        async with Client(mcp) as client:
            return await client.call_tool("generate_dsl", {"file_path": FLAT})

    result = _run(go())
    assert result.data["roots"][0]["name"] == "CUSTOMER-RECORD"


def test_recommend_type_mapping_tool() -> None:
    async def go():  # type: ignore[no-untyped-def]
        async with Client(mcp) as client:
            return await client.call_tool(
                "recommend_type_mapping", {"file_path": FLAT, "target": "go"}
            )

    result = _run(go())
    assert len(result.data["fields"]) == 3


def test_full_override_generate_validate_report_sequence(tmp_path: Path) -> None:
    overrides_file = str(tmp_path / "overrides.json")

    async def go():  # type: ignore[no-untyped-def]
        async with Client(mcp) as client:
            for field, choice in (
                ("FINANCIAL-RECORD.SENSOR-READING", "float32"),
                ("FINANCIAL-RECORD.PRECISE-READING", "float64"),
            ):
                await client.call_tool(
                    "update_mapping_override",
                    {
                        "file_path": MIXED, "target": "go", "field_path": field,
                        "choice": choice, "reason": "best-effort", "force": True,
                        "overrides_file": overrides_file,
                    },
                )

            files = await client.call_tool(
                "generate_target_code",
                {"file_path": MIXED, "target": "go", "overrides_file": overrides_file},
            )
            findings = await client.call_tool(
                "validate_conversion",
                {"file_path": MIXED, "target": "go", "overrides_file": overrides_file},
            )
            report = await client.call_tool(
                "generate_conversion_report",
                {"file_path": MIXED, "target": "go", "overrides_file": overrides_file},
            )
            return files, findings, report

    files, findings, report = _run(go())
    assert "gen.go" in files.data
    assert "float32" in files.data["gen.go"]
    assert not any(f["code"] == "missing-from-output" for f in findings.data["findings"])
    assert "# Conversion report (go)" in report.data


def test_update_mapping_override_rejects_an_invalid_status_candidate_without_force(
    tmp_path: Path,
) -> None:
    # Regression: the tool used to build valid_choices from the
    # unfiltered candidate_names(), so "double" (a real but "invalid"
    # candidate for UNIT-PRICE under java) silently passed without force.
    overrides_file = str(tmp_path / "overrides.json")

    async def go():  # type: ignore[no-untyped-def]
        async with Client(mcp) as client:
            await client.call_tool(
                "update_mapping_override",
                {
                    "file_path": MIXED, "target": "java",
                    "field_path": "FINANCIAL-RECORD.UNIT-PRICE",
                    "choice": "double", "reason": "no",
                    "overrides_file": overrides_file,
                },
            )

    with pytest.raises(Exception, match="not a valid candidate"):
        _run(go())


def test_unknown_tool_raises() -> None:
    async def go():  # type: ignore[no-untyped-def]
        async with Client(mcp) as client:
            await client.call_tool("not_a_real_tool", {})

    with pytest.raises(Exception):  # noqa: B017 - FastMCP's own tool-not-found error
        _run(go())

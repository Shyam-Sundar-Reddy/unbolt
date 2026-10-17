from pathlib import Path

import pytest

from unbolt.dsl import build_dsl
from unbolt.parser import parse_copybook

FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDEN_DIR = Path(__file__).parent / "golden"

FIXTURE_NAMES = [p.stem for p in sorted(FIXTURES_DIR.glob("*.cpy"))]


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_dsl_json_matches_golden_file(name: str) -> None:
    source = (FIXTURES_DIR / f"{name}.cpy").read_text()
    result = parse_copybook(source)
    assert result.diagnostics == ()

    dsl = build_dsl(result, source_file=f"{name}.cpy")
    expected = (GOLDEN_DIR / f"{name}.json").read_text()

    assert dsl.to_json() == expected


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_dsl_json_round_trips_through_from_json(name: str) -> None:
    source = (FIXTURES_DIR / f"{name}.cpy").read_text()
    result = parse_copybook(source)
    dsl = build_dsl(result, source_file=f"{name}.cpy")

    restored = type(dsl).from_json(dsl.to_json())

    assert restored == dsl


def test_parsing_the_same_source_twice_is_byte_identical() -> None:
    source = (FIXTURES_DIR / "mixed_usage.cpy").read_text()
    first = build_dsl(parse_copybook(source), source_file="mixed_usage.cpy").to_json()
    second = build_dsl(parse_copybook(source), source_file="mixed_usage.cpy").to_json()
    assert first == second

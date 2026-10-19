from pathlib import Path

import pytest

from unbolt.dsl import build_dsl
from unbolt.generators import generate_code
from unbolt.mapping import recommend_mappings
from unbolt.overrides import Overrides, apply_override
from unbolt.parser import parse_copybook

FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDEN_DIR = Path(__file__).parent / "golden_codegen"
FIXTURE_NAMES = [p.stem for p in sorted(FIXTURES_DIR.glob("*.cpy"))]


def _overrides_for(name: str, target: str) -> Overrides:
    if name != "mixed_usage":
        return Overrides()
    float_type, double_type = ("float32", "float64") if target == "go" else ("float", "double")
    reason = "best-effort IEEE754 approximation (goal.md section 5.4)"
    overrides = apply_override(
        Overrides(),
        "FINANCIAL-RECORD.SENSOR-READING",
        float_type,
        reason,
        valid_choices=[],
        force=True,
    )
    return apply_override(
        overrides,
        "FINANCIAL-RECORD.PRECISE-READING",
        double_type,
        reason,
        valid_choices=[],
        force=True,
    )


@pytest.mark.parametrize("target", ["go", "java"])
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_generated_code_matches_golden_files(name: str, target: str) -> None:
    source = (FIXTURES_DIR / f"{name}.cpy").read_text()
    dsl = build_dsl(parse_copybook(source), source_file=f"{name}.cpy")
    report = recommend_mappings(dsl, target)
    files = generate_code(dsl, report, target, overrides=_overrides_for(name, target))

    golden_dir = GOLDEN_DIR / target / name
    expected_files = {p.name for p in golden_dir.iterdir()}
    assert set(files) == expected_files

    for rel_path, content in files.items():
        assert content == (golden_dir / rel_path).read_text()


@pytest.mark.parametrize("target", ["go", "java"])
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_generating_twice_is_byte_identical(name: str, target: str) -> None:
    source = (FIXTURES_DIR / f"{name}.cpy").read_text()

    def run() -> dict[str, str]:
        dsl = build_dsl(parse_copybook(source), source_file=f"{name}.cpy")
        report = recommend_mappings(dsl, target)
        return generate_code(dsl, report, target, overrides=_overrides_for(name, target))

    assert run() == run()

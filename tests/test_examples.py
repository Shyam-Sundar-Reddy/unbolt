import subprocess
import sys
from pathlib import Path

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def test_quickstart_example_runs_end_to_end_with_no_findings() -> None:
    result = subprocess.run(
        [sys.executable, str(EXAMPLES_DIR / "quickstart.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "type CustomerRecord struct" in result.stdout
    assert "## Findings" in result.stdout

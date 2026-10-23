import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("check_docs", ROOT / "tools" / "check_docs.py")
assert spec is not None and spec.loader is not None
check_docs = importlib.util.module_from_spec(spec)
sys.modules["check_docs"] = check_docs
spec.loader.exec_module(check_docs)


def test_no_dead_links_in_tracked_markdown() -> None:
    assert check_docs.check_links() == []


def test_generated_docs_are_not_stale() -> None:
    assert check_docs.check_generated_docs_are_fresh() == []

"""CI docs check (phase.md Phase 7 step 4): every relative markdown link
in a tracked .md file resolves to a real file, and the two fully
reproducible generated docs (mapping-rules.md, diagnostics.md) match
what their generator currently produces - catching exactly the kind of
drift this project hit firsthand (supported-constructs.md claiming
COMP-5/level-88/edited-pictures behavior that wasn't true). Not
markdownlint/a link-check service: stdlib only, no new dependency for
what two small scripts already cover.

docs/performance.md is excluded from the regeneration diff - its
numbers vary run to run by design (real timings), so diffing it against
a fresh run would fail on noise, not drift.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_TRACKED_MD = ["README.md", "CONTRIBUTING.md", "CHANGELOG.md"]
_REGENERATE = {
    "docs/mapping-rules.md": ["tools/gen_mapping_rules_doc.py"],
    "docs/diagnostics.md": ["tools/gen_diagnostics_doc.py"],
}


def _tracked_docs() -> list[Path]:
    # --cached --others --exclude-standard: tracked files AND untracked
    # files that git would actually let you add (i.e. not gitignored) -
    # plain `git ls-files` alone misses a brand-new file before its
    # first `git add`, which would otherwise escape this check entirely
    # on the one run that matters most (right before committing it).
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "docs/*.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def check_links() -> list[str]:
    errors = []
    for md_path in [ROOT / p for p in _TRACKED_MD] + _tracked_docs():
        if not md_path.exists():
            continue
        text = md_path.read_text(encoding="utf-8")
        for target in _LINK.findall(text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            resolved = (md_path.parent / target.split("#")[0]).resolve()
            if not resolved.exists():
                errors.append(f"{md_path.relative_to(ROOT)}: dead link to {target!r}")
    return errors


def check_generated_docs_are_fresh() -> list[str]:
    errors = []
    for doc_path, generator in _REGENERATE.items():
        before = (ROOT / doc_path).read_text(encoding="utf-8")
        subprocess.run([sys.executable, *generator], cwd=ROOT, check=True, capture_output=True)
        after = (ROOT / doc_path).read_text(encoding="utf-8")
        if before != after:
            errors.append(f"{doc_path} is stale - run `python {generator[0]}` and commit it")
            (ROOT / doc_path).write_text(before, encoding="utf-8")  # restore; CI shouldn't edit
    return errors


def main() -> int:
    errors = check_links() + check_generated_docs_are_fresh()
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        return 1
    print("docs check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

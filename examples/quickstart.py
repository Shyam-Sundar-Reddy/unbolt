"""Reproduces the README's 30-second demo, end to end, as runnable code
rather than a copy-pasted transcript that can quietly drift from the
truth. Run: uv run python examples/quickstart.py
"""

from unbolt.dsl import build_dsl
from unbolt.generators import generate_code
from unbolt.mapping import recommend_mappings
from unbolt.parser import parse_copybook
from unbolt.reporting import build_report, render_markdown
from unbolt.validation import validate_conversion

COPYBOOK = """
01  CUSTOMER-RECORD.
    05  CUSTOMER-ID         PIC 9(6).
    05  CUSTOMER-AGE        PIC S9(3).
    05  ACCOUNT-BALANCE     PIC S9(7)V99.
"""


def main() -> None:
    dsl = build_dsl(parse_copybook(COPYBOOK), source_file="account.cpy")
    mapping = recommend_mappings(dsl, "go")
    files = generate_code(dsl, mapping, "go")

    print("=== generated Go ===")
    print(files["gen.go"])

    validation = validate_conversion(dsl, mapping, files)
    assert validation.findings == (), f"unexpected findings: {validation.findings}"

    report = build_report(dsl, mapping, validation)
    balance_entry = next(e for e in report.entries if e.field_path.endswith("ACCOUNT-BALANCE"))

    print("=== why ACCOUNT-BALANCE became", balance_entry.chosen_type, "===")
    print(balance_entry.rationale)

    print(render_markdown(report))


if __name__ == "__main__":
    main()

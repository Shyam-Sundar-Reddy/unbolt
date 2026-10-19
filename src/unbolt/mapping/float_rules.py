"""COMP-1/COMP-2: goal.md §5.4 - IBM hexadecimal floating point, not IEEE
754. Flagged with a single needs-policy candidate, identical for every
target - this caveat isn't Go- or Java-specific, and there is no safe
default, so it's never auto-mapped.
"""

from unbolt.mapping.model import Candidate


def float_needs_policy_candidates(usage: str) -> tuple[Candidate, ...]:
    return (
        Candidate(
            type_name=f"<{usage}-needs-policy>",
            status="needs-policy",
            rule_id="float-needs-policy",
            rationale=(
                f"{usage} is IBM hexadecimal floating point, not IEEE 754; "
                "no safe default without an explicit reviewed policy (goal.md §5.4)"
            ),
        ),
    )

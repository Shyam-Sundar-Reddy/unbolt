"""recommend_mappings: every field, every candidate, never just a winner.

goal.md's signature sketch is recommend_mappings(dsl, target, rules,
overrides); this phase doesn't implement a pluggable rule-set or
override-aware reporting yet - there's no real consumer for either (no
second rule set to plug in, and a candidate's type-fit is a fact about
ranges, independent of what a human later picks). Both stay future scope
rather than unused parameters that would do nothing today.
"""

from unbolt.datatypes import TypeFacts, describe_datatype
from unbolt.datatypes.sizing import is_alpha_pic
from unbolt.dsl.schema import Dsl, FieldNode
from unbolt.exceptions import UnknownTargetError
from unbolt.mapping.go_rules import go_decimal_candidates, go_integer_candidates
from unbolt.mapping.java_rules import java_decimal_candidates, java_integer_candidates
from unbolt.mapping.model import Candidate, FieldMapping, MappingReport

RULE_SET_VERSION = "0"

_INTEGER_RULES = {
    "go": go_integer_candidates,
    "java": java_integer_candidates,
}
_DECIMAL_RULES = {
    "go": go_decimal_candidates,
    "java": java_decimal_candidates,
}


def recommend_mappings(dsl: Dsl, target: str) -> MappingReport:
    if target not in _INTEGER_RULES:
        raise UnknownTargetError(f"unknown target {target!r}; expected 'go' or 'java'")

    integer_rule = _INTEGER_RULES[target]
    decimal_rule = _DECIMAL_RULES[target]

    fields: list[FieldMapping] = []

    def walk(node: FieldNode, path: str) -> None:
        field_path = f"{path}.{node.name}" if path else node.name
        if node.pic is not None and not is_alpha_pic(node.pic):
            facts: TypeFacts = describe_datatype(node)
            candidates: tuple[Candidate, ...] = (
                decimal_rule(facts) if facts.scale > 0 else integer_rule(facts)
            )
            fields.append(FieldMapping(field_path=field_path, candidates=candidates))
        for child in node.children:
            walk(child, field_path)

    for root in dsl.roots:
        walk(root, "")

    return MappingReport(target=target, fields=tuple(fields))

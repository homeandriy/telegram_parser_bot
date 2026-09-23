"""Deterministic alert rules; no AI classification is used for critical alerts."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .models import AlertEvent, TelegramMessage
from ..core.runtime import DEFAULT_RULE_LOCATION_UID


@dataclass(frozen=True)
class ScenarioMatch:
    index: int
    action: dict
    matched_terms: tuple[str, ...]
    rule_id: str
    rule_title: str


@dataclass(frozen=True)
class RuleDescriptor:
    id: str
    title: str
    location_uid: str
    matching_mode: str
    terms: tuple[str, ...]
    excluded_terms: tuple[str, ...]


def evaluate_scenarios(message: TelegramMessage, rule: dict) -> list[ScenarioMatch]:
    """Evaluate UI scenarios case-insensitively.

    The root's direct items are the first scenario. Groups created by
    ``Додати сценарій`` are independent additional scenarios.
    """
    direct_items = [item for item in rule.get("items", []) if not item.get("scenario")]
    scenarios: list[dict] = []
    if direct_items:
        scenarios.append({"operator": rule.get("operator", "and"), "items": direct_items, "action": rule.get("action", {})})
    scenarios.extend(item for item in rule.get("items", []) if item.get("scenario"))
    matches: list[ScenarioMatch] = []
    for index, scenario in enumerate(scenarios, start=1):
        matched, terms = match_node(message.text, scenario)
        if matched:
            matches.append(
                ScenarioMatch(
                    index,
                    scenario.get("action", {}),
                    tuple(terms),
                    str(scenario.get("id", f"scenario-{index}")),
                    str(scenario.get("title", f"Сценарій {index}")),
                )
            )
    return matches


def describe_scenarios(rule: dict) -> list[RuleDescriptor]:
    """Return stable API-facing identifiers for the configured scenarios."""
    direct_items = [item for item in rule.get("items", []) if not item.get("scenario")]
    scenarios: list[dict] = []
    if direct_items:
        scenarios.append({"id": "scenario-1", "title": "Сценарій 1", "action": rule.get("action", {})})
    scenarios.extend(item for item in rule.get("items", []) if item.get("scenario"))
    return [
        RuleDescriptor(
            id=str(scenario.get("id", f"scenario-{index}")),
            title=str(scenario.get("title", f"Сценарій {index}")),
            location_uid=str(scenario.get("action", rule.get("action", {})).get("location_uid", DEFAULT_RULE_LOCATION_UID)).strip() or DEFAULT_RULE_LOCATION_UID,
            matching_mode="all" if scenario.get("operator", "and") == "and" else "any",
            terms=_scenario_terms(scenario),
            excluded_terms=_scenario_terms(scenario, "excluded"),
        )
        for index, scenario in enumerate(scenarios, start=1)
    ]


def _scenario_terms(node: dict, category: str = "positive") -> tuple[str, ...]:
    """Collect configured terms without changing matching behavior."""
    if category == "positive":
        operator = node.get("operator", "and")
        return tuple(
            expression
            for child in node.get("items", [])
            if isinstance(child, dict)
            if (expression := _positive_expression(child, operator)) is not None
        )

    if node.get("type") == "condition":
        value = str(node.get("value", "")).strip()
        is_excluded = node.get("mode") == "not_contains"
        if not value or not is_excluded:
            return ()
        return (value,)

    terms: list[str] = []
    for child in node.get("items", []):
        if isinstance(child, dict):
            for value in _scenario_terms(child, category):
                if value not in terms:
                    terms.append(value)
    return tuple(terms)


def _positive_expression(node: dict, parent_operator: str | None = None) -> str | None:
    if node.get("type") == "condition":
        value = str(node.get("value", "")).strip()
        return value if value and node.get("mode") != "not_contains" else None

    operator = node.get("operator", "and")
    expressions = [
        expression
        for child in node.get("items", [])
        if isinstance(child, dict)
        if (expression := _positive_expression(child, operator)) is not None
    ]
    if not expressions:
        return None
    expression = (" І " if operator == "and" else " АБО ").join(expressions)
    if len(expressions) > 1 and parent_operator is not None and operator != parent_operator:
        return f"({expression})"
    return expression


def match_node(text: str, node: dict) -> tuple[bool, list[str]]:
    normalized = text.casefold()
    if node.get("type") == "condition":
        value = str(node.get("value", "")).strip()
        mode = node.get("mode", "contains")
        if mode == "contains_word":
            contains = re.search(rf"(?<!\w){re.escape(value.casefold())}(?!\w)", normalized) is not None
        else:
            contains = value.casefold() in normalized
        result = not contains if mode == "not_contains" else contains
        return result, [value] if result and value else []
    results = [match_node(text, child) for child in node.get("items", [])]
    if not results:
        return False, []
    matched = all(result for result, _ in results) if node.get("operator", "and") == "and" else any(result for result, _ in results)
    return matched, [term for result, terms in results if result for term in terms]


def evaluate(message: TelegramMessage, escalation: tuple[str, ...], critical: tuple[str, ...]) -> AlertEvent | None:
    text = message.text.casefold()
    for pattern in critical:
        if pattern.casefold() in text:
            return AlertEvent(message, "critical", pattern)
    for pattern in escalation:
        if pattern.casefold() in text:
            return AlertEvent(message, "escalation", pattern)
    return None

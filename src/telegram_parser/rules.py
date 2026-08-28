"""Deterministic alert rules; no AI classification is used for critical alerts."""

from __future__ import annotations

from dataclasses import dataclass

from .models import AlertEvent, TelegramMessage


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
        scenarios.append({"id": "scenario-1", "title": "Сценарій 1"})
    scenarios.extend(item for item in rule.get("items", []) if item.get("scenario"))
    return [
        RuleDescriptor(str(scenario.get("id", f"scenario-{index}")), str(scenario.get("title", f"Сценарій {index}")))
        for index, scenario in enumerate(scenarios, start=1)
    ]


def match_node(text: str, node: dict) -> tuple[bool, list[str]]:
    normalized = text.casefold()
    if node.get("type") == "condition":
        value = str(node.get("value", "")).strip()
        contains = value.casefold() in normalized
        result = contains if node.get("mode") == "contains" else not contains
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

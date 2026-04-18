"""Unit tests for :class:`lst.detector.rules.high_risk.HighRiskPatternRule`."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from lst.detector.rules.high_risk import HighRiskPatternRule
from lst.schemas import AggregatedTemplate, FlagCategory


@pytest.fixture
def rule() -> HighRiskPatternRule:
    return HighRiskPatternRule()


def test_high_risk_fires_on_template_match(
    rule: HighRiskPatternRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """A kernel panic in the template text fires the rule at score 0.8."""
    aggregated = make_aggregated(template="kernel panic - not syncing: <*>")
    event = rule.evaluate(aggregated)
    assert event is not None
    assert event.category is FlagCategory.HIGH_RISK_PATTERN
    assert event.rule_name == "high_risk_keyword_match"
    assert event.score == pytest.approx(0.8)


def test_high_risk_falls_back_to_sample_lines(
    rule: HighRiskPatternRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Keyword hidden in sample_lines still triggers the rule."""
    aggregated = make_aggregated(
        template="generic event <*>",
        sample_lines=["an otherwise bland line kernel panic hidden within"],
    )
    event = rule.evaluate(aggregated)
    assert event is not None
    assert event.context_notes is not None
    assert "sample_lines" in event.context_notes


def test_high_risk_does_not_fire_on_clean_template(
    rule: HighRiskPatternRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Templates without any IOC keyword return ``None``."""
    aggregated = make_aggregated(
        template="routine message <*>",
        sample_lines=["nothing suspicious here"],
    )
    assert rule.evaluate(aggregated) is None


def test_high_risk_context_notes_name_the_matched_keyword(
    rule: HighRiskPatternRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """The matched keyword name is surfaced for downstream reporting."""
    aggregated = make_aggregated(
        template="sshd[<*>]: POSSIBLE BREAK-IN ATTEMPT from <*>",
    )
    event = rule.evaluate(aggregated)
    assert event is not None
    assert event.context_notes is not None
    assert "break_in_attempt" in event.context_notes


def test_high_risk_exposes_non_empty_pt_description(rule: HighRiskPatternRule) -> None:
    """``description_pt`` is a non-empty string the Reporter can surface."""
    assert isinstance(rule.description_pt, str)
    assert rule.description_pt.strip() != ""

"""Unit tests for :class:`lst.detector.rules.variety.VarietyRule`."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from lst.detector.rules.variety import VarietyRule
from lst.schemas import AggregatedTemplate, FlagCategory


@pytest.fixture
def rule() -> VarietyRule:
    return VarietyRule()


def test_variety_fires_when_many_ips_and_no_auth_verb(
    rule: VarietyRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """5 unique IPs over 6 events, no auth verb -> a classic probe pattern."""
    aggregated = make_aggregated(
        template="Handshake initiated from <*>",
        total_count=6,
        unique_ips=5,
    )
    event = rule.evaluate(aggregated)
    assert event is not None
    assert event.category is FlagCategory.VARIETY
    assert event.rule_name == "source_variety_no_auth_context"


def test_variety_skips_success_phrased_templates(
    rule: VarietyRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Templates with a success verb are benign auth traffic."""
    aggregated = make_aggregated(
        template="Accepted handshake from <*>",
        total_count=6,
        unique_ips=6,
    )
    assert rule.evaluate(aggregated) is None


def test_variety_skips_fail_phrased_templates(
    rule: VarietyRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Templates with a fail verb belong to BruteForceRule's domain."""
    aggregated = make_aggregated(
        template="Failed handshake from <*>",
        total_count=6,
        unique_ips=6,
    )
    assert rule.evaluate(aggregated) is None


def test_variety_skips_when_ip_cardinality_below_threshold(
    rule: VarietyRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Fewer than 5 distinct IPs can't sustain a variety signal."""
    aggregated = make_aggregated(
        template="Handshake from <*>",
        total_count=4,
        unique_ips=4,
    )
    assert rule.evaluate(aggregated) is None


def test_variety_skips_when_ratio_is_low(
    rule: VarietyRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Ratio < 0.5 means repeat traffic dominates -- no variety signal."""
    aggregated = make_aggregated(
        template="Handshake from <*>",
        total_count=20,
        unique_ips=5,
    )
    assert rule.evaluate(aggregated) is None


def test_variety_score_scales_with_ip_cardinality(
    rule: VarietyRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """30+ IPs saturates the variety score at 1.0."""
    aggregated = make_aggregated(
        template="Handshake from <*>",
        total_count=30,
        unique_ips=30,
    )
    event = rule.evaluate(aggregated)
    assert event is not None
    assert event.score == pytest.approx(1.0)


def test_variety_context_notes_state_no_verb_observation(
    rule: VarietyRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Notes call out the no-auth-verb condition explicitly."""
    aggregated = make_aggregated(
        template="Request on <*>",
        total_count=8,
        unique_ips=8,
    )
    event = rule.evaluate(aggregated)
    assert event is not None
    assert event.context_notes is not None
    assert "no auth verb" in event.context_notes


def test_variety_exposes_non_empty_pt_description(rule: VarietyRule) -> None:
    """``description_pt`` is a non-empty string the Reporter can surface."""
    assert isinstance(rule.description_pt, str)
    assert rule.description_pt.strip() != ""

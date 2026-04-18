"""Unit tests for :class:`lst.detector.rules.brute_force.BruteForceRule`."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from lst.detector.rules.brute_force import BruteForceRule
from lst.schemas import AggregatedTemplate, FlagCategory


@pytest.fixture
def rule() -> BruteForceRule:
    return BruteForceRule()


def test_brute_force_fires_on_ip_diverse_failures(
    rule: BruteForceRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """15 distinct IPs over 15 failed events with a fail-verb template fires."""
    aggregated = make_aggregated(
        template="Failed password for <*> from <*> port 22 ssh2",
        total_count=15,
        unique_ips=15,
    )
    event = rule.evaluate(aggregated)
    assert event is not None
    assert event.category is FlagCategory.BRUTE_FORCE
    assert event.rule_name == "brute_force_by_ip_cardinality"
    assert event.score == pytest.approx(0.75)


def test_brute_force_skips_when_ip_cardinality_below_threshold(
    rule: BruteForceRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Fewer than 10 unique IPs means we lack evidence of distributed sources."""
    aggregated = make_aggregated(
        template="Failed password for <*> from <*> port 22 ssh2",
        total_count=9,
        unique_ips=9,
    )
    assert rule.evaluate(aggregated) is None


def test_brute_force_skips_on_low_ip_ratio(
    rule: BruteForceRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Enough IPs in absolute terms but repeat-hit dominant -> not brute-force."""
    aggregated = make_aggregated(
        template="Failed password for <*> from <*> port 22 ssh2",
        total_count=50,
        unique_ips=10,
    )
    assert rule.evaluate(aggregated) is None


def test_brute_force_skips_when_template_lacks_fail_verb(
    rule: BruteForceRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Success-phrased templates are not brute-force, even with many IPs."""
    aggregated = make_aggregated(
        template="Accepted password for <*> from <*> port 22 ssh2",
        total_count=15,
        unique_ips=15,
    )
    assert rule.evaluate(aggregated) is None


def test_brute_force_score_saturates_at_twenty_ips(
    rule: BruteForceRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """At 20+ distinct IPs the score is clamped to 1.0."""
    aggregated = make_aggregated(
        template="Failed password for <*> from <*>",
        total_count=25,
        unique_ips=25,
    )
    event = rule.evaluate(aggregated)
    assert event is not None
    assert event.score == pytest.approx(1.0)


def test_brute_force_context_notes_report_counts_and_ratio(
    rule: BruteForceRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Notes surface both cardinality and ratio so the Explainer has context."""
    aggregated = make_aggregated(
        template="Failed password for <*> from <*>",
        total_count=12,
        unique_ips=12,
    )
    event = rule.evaluate(aggregated)
    assert event is not None
    assert event.context_notes is not None
    assert "12" in event.context_notes
    assert "ratio" in event.context_notes.lower()


def test_brute_force_exposes_non_empty_pt_description(rule: BruteForceRule) -> None:
    """``description_pt`` is a non-empty string the Reporter can surface."""
    assert isinstance(rule.description_pt, str)
    assert rule.description_pt.strip() != ""

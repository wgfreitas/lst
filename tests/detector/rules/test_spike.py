"""Unit tests for :class:`lst.detector.rules.spike.SpikeRule`.

Notable: the relative-trigger arm requires both ``peak >= rate * 3`` AND
``peak >= 3.0``. The absolute floor is intentional -- very-low-rate
clusters (e.g. rate 0.25/min, peak 1/min) satisfy the relative ratio
trivially but are ordinary low-volume noise, not spikes.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from lst.detector.rules.spike import SpikeRule
from lst.schemas import AggregatedTemplate, FlagCategory


@pytest.fixture
def rule() -> SpikeRule:
    return SpikeRule()


def test_spike_fires_on_absolute_peak(
    rule: SpikeRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Peak >= 5/min fires regardless of the mean rate."""
    aggregated = make_aggregated(
        total_count=10,
        rate_per_minute=0.5,
        peak_rate_per_minute=5.0,
    )
    event = rule.evaluate(aggregated)
    assert event is not None
    assert event.category is FlagCategory.SPIKE
    assert event.rule_name == "rate_spike_3sigma_or_absolute"
    assert event.score == pytest.approx(1.0)


def test_spike_fires_on_relative_peak_above_floor(
    rule: SpikeRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Peak 4/min over mean 1/min fires (4x ratio AND peak >= 3.0 floor)."""
    aggregated = make_aggregated(
        total_count=10,
        rate_per_minute=1.0,
        peak_rate_per_minute=4.0,
    )
    event = rule.evaluate(aggregated)
    assert event is not None
    assert event.score == pytest.approx(0.4)


def test_spike_ignores_low_peak_even_with_huge_relative_ratio(
    rule: SpikeRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Peak 1/min over mean 0.25/min is a 4x ratio but not a spike."""
    aggregated = make_aggregated(
        total_count=15,
        rate_per_minute=0.25,
        peak_rate_per_minute=1.0,
    )
    assert rule.evaluate(aggregated) is None


def test_spike_skips_when_peak_and_ratio_both_insufficient(
    rule: SpikeRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Peak 4 with mean 2 is only 2x and below absolute floor -- no spike."""
    aggregated = make_aggregated(
        total_count=10,
        rate_per_minute=2.0,
        peak_rate_per_minute=4.0,
    )
    assert rule.evaluate(aggregated) is None


def test_spike_requires_minimum_total_count(
    rule: SpikeRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Two-event clusters never produce spike flags, even at peak=5."""
    aggregated = make_aggregated(
        total_count=2,
        rate_per_minute=0.5,
        peak_rate_per_minute=5.0,
    )
    assert rule.evaluate(aggregated) is None


def test_spike_context_notes_include_peak_and_mean(
    rule: SpikeRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Notes surface both the peak and the mean so reports stay self-explanatory."""
    aggregated = make_aggregated(
        total_count=10,
        rate_per_minute=0.5,
        peak_rate_per_minute=6.0,
    )
    event = rule.evaluate(aggregated)
    assert event is not None
    assert event.context_notes is not None
    assert "peak" in event.context_notes.lower()
    assert "0.50" in event.context_notes


def test_spike_exposes_non_empty_pt_description(rule: SpikeRule) -> None:
    """``description_pt`` is a non-empty string the Reporter can surface."""
    assert isinstance(rule.description_pt, str)
    assert rule.description_pt.strip() != ""

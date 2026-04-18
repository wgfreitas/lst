"""Unit tests for :class:`lst.detector.rules.novelty.NoveltyRule`."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from lst.detector.rules.novelty import NoveltyRule
from lst.schemas import AggregatedTemplate, FlagCategory


@pytest.fixture
def rule() -> NoveltyRule:
    return NoveltyRule()


def test_novelty_fires_on_singleton_with_base_score(
    rule: NoveltyRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """``total_count == 1`` + benign template -> base score 0.6."""
    aggregated = make_aggregated(total_count=1, template="something harmless <*>")
    event = rule.evaluate(aggregated)
    assert event is not None
    assert event.category is FlagCategory.NOVELTY
    assert event.rule_name == "novelty_singleton"
    assert event.score == pytest.approx(0.6)


def test_novelty_boosts_score_on_high_risk_keyword(
    rule: NoveltyRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """High-risk keyword in template lifts the score to 0.9."""
    aggregated = make_aggregated(
        total_count=1,
        template="reverse mapping failed - POSSIBLE BREAK-IN ATTEMPT!",
    )
    event = rule.evaluate(aggregated)
    assert event is not None
    assert event.score == pytest.approx(0.9)
    assert event.context_notes is not None
    assert "break_in_attempt" in event.context_notes


def test_novelty_does_not_fire_when_total_count_greater_than_one(
    rule: NoveltyRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Non-singleton clusters are outside the rule's scope."""
    aggregated = make_aggregated(total_count=2, template="repeated template <*>")
    assert rule.evaluate(aggregated) is None


def test_novelty_context_notes_include_total_count_hint(
    rule: NoveltyRule,
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Benign singleton notes mention the trigger without exposing internals."""
    aggregated = make_aggregated(total_count=1, template="ordinary debug line <*>")
    event = rule.evaluate(aggregated)
    assert event is not None
    assert event.context_notes is not None
    assert "singleton" in event.context_notes.lower()
    assert "total_count=1" in event.context_notes


def test_novelty_exposes_non_empty_pt_description(rule: NoveltyRule) -> None:
    """``description_pt`` is a non-empty string the Reporter can surface."""
    assert isinstance(rule.description_pt, str)
    assert rule.description_pt.strip() != ""

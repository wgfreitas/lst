"""Integration tests for :func:`lst.detector.engine.detect`.

Exercises the engine on the static fixture via the full pipeline
(Parser -> Aggregator -> Detector) plus synthetic single-template
inputs for dedup and tie-break behaviour.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from lst.aggregator import aggregate
from lst.detector import detect
from lst.parser import iter_log_lines, mine_templates
from lst.schemas import AggregatedTemplate, FlagCategory

FIXTURE = Path(__file__).parent.parent / "fixtures" / "auth_sample.log"


def test_detect_empty_input_returns_empty_list() -> None:
    """An empty batch produces no flags (engine is total over its input)."""
    assert detect([]) == []


def test_detect_returns_nothing_for_unmatched_input(
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """A cluster no rule recognises produces an empty flag list."""
    boring = make_aggregated(
        template="wholly unremarkable <*>",
        total_count=2,
        unique_ips=0,
    )
    assert detect([boring]) == []


def test_detect_end_to_end_on_fixture_produces_three_flags() -> None:
    """Static fixture yields exactly 3 flags with expected categories."""
    templates, mined_lines = mine_templates(iter_log_lines(FIXTURE))
    aggregated = aggregate(templates, mined_lines)

    flags = detect(aggregated)
    assert len(flags) == 3

    categories = [flag.category for flag in flags]
    assert categories.count(FlagCategory.BRUTE_FORCE) == 1
    assert categories.count(FlagCategory.NOVELTY) == 2

    templates_flagged = [flag.aggregated.template.template for flag in flags]
    assert any("Failed password" in text for text in templates_flagged)
    assert any("POSSIBLE BREAK-IN" in text for text in templates_flagged)


def test_detect_output_is_sorted_by_score_desc(
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Results come back highest-score-first."""
    strong = make_aggregated(
        cluster_id=1,
        template="Failed password for <*> from <*>",
        total_count=20,
        unique_ips=20,
    )
    weak = make_aggregated(
        cluster_id=2,
        total_count=1,
        template="ordinary singleton <*>",
    )
    flags = detect([weak, strong])
    scores = [flag.score for flag in flags]
    assert scores == sorted(scores, reverse=True)
    assert flags[0].aggregated.template.cluster_id == 1


def test_detect_dedupes_same_cluster_keeping_highest_score(
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """One cluster, two matching rules -> the higher-score event wins."""
    singleton_with_keyword = make_aggregated(
        cluster_id=42,
        total_count=1,
        template="POSSIBLE BREAK-IN ATTEMPT from <*>",
    )
    flags = detect([singleton_with_keyword])
    assert len(flags) == 1
    assert flags[0].category is FlagCategory.NOVELTY
    assert flags[0].score == 0.9


def test_detect_tie_break_prefers_higher_priority_category(
    make_aggregated: Callable[..., AggregatedTemplate],
) -> None:
    """Equal scores -> BRUTE_FORCE outranks HIGH_RISK_PATTERN."""
    aggregated = make_aggregated(
        cluster_id=7,
        template="Failed authentication POSSIBLE BREAK-IN ATTEMPT for <*>",
        total_count=20,
        unique_ips=16,
    )
    flags = detect([aggregated])
    assert len(flags) == 1
    assert flags[0].category is FlagCategory.BRUTE_FORCE
    assert flags[0].score == 0.8

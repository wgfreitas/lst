"""Unit tests for the pipeline schemas in ``lst.schemas``.

Covers happy-path instantiation, cross-field validators, strict datetime
handling, frozen-model enforcement, and JSON round-trip for the terminal
schema consumed by the Reporter.
"""

from typing import Any

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from lst.schemas import (
    AggregatedTemplate,
    ExplainedEvent,
    FlagCategory,
    FlaggedEvent,
    LogTemplate,
    Severity,
)

T_START = datetime(2026, 4, 18, 10, 0, 0, tzinfo=UTC)
T_END = datetime(2026, 4, 18, 11, 0, 0, tzinfo=UTC)
T_FLAGGED = datetime(2026, 4, 18, 11, 5, 0, tzinfo=UTC)
T_EXPLAINED = datetime(2026, 4, 18, 11, 5, 30, tzinfo=UTC)


@pytest.fixture
def log_template() -> LogTemplate:
    """A valid ``LogTemplate`` representing SSH auth failures."""
    return LogTemplate(
        cluster_id=1,
        template="Failed password for <*> from <*> port <*>",
        size=3,
        sample_lines=[
            "Failed password for root from 1.2.3.4 port 22",
            "Failed password for admin from 5.6.7.8 port 22",
            "Failed password for user from 9.10.11.12 port 22",
        ],
        first_seen=T_START,
        last_seen=T_END,
    )


@pytest.fixture
def aggregated_template(log_template: LogTemplate) -> AggregatedTemplate:
    """A valid ``AggregatedTemplate`` wrapping ``log_template``."""
    return AggregatedTemplate(
        template=log_template,
        total_count=42,
        rate_per_minute=0.7,
        peak_rate_per_minute=2.5,
        unique_ips=3,
        unique_users=2,
        sample_ips=["1.2.3.4", "5.6.7.8", "9.10.11.12"],
        sample_users=["root", "admin"],
    )


@pytest.fixture
def flagged_event(aggregated_template: AggregatedTemplate) -> FlaggedEvent:
    """A valid ``FlaggedEvent`` flagged by the brute-force rule."""
    return FlaggedEvent(
        aggregated=aggregated_template,
        category=FlagCategory.BRUTE_FORCE,
        rule_name="brute_force_v1",
        score=0.85,
        triggered_at=T_FLAGGED,
        context_notes="3 IPs hit 42 times in 1h",
    )


@pytest.fixture
def explained_event(flagged_event: FlaggedEvent) -> ExplainedEvent:
    """A valid ``ExplainedEvent`` enriched by the LLM."""
    return ExplainedEvent(
        flagged=flagged_event,
        explanation="Tentativa de brute-force detectada: multiplos IPs e usuarios em 1h.",
        severity=Severity.HIGH,
        next_action="Bloquear IPs ofensivos no firewall e revisar logs adjacentes.",
        llm_model="gpt-oss:120b",
        llm_latency_ms=1240,
        explained_at=T_EXPLAINED,
    )


# LogTemplate -----------------------------------------------------------------


def test_log_template_valid(log_template: LogTemplate) -> None:
    """Happy path: all fields preserved and exposed."""
    assert log_template.cluster_id == 1
    assert log_template.size == 3
    assert len(log_template.sample_lines) == 3
    assert log_template.first_seen.tzinfo is not None


def test_log_template_rejects_reversed_timeline() -> None:
    """``last_seen`` before ``first_seen`` must fail the model validator."""
    with pytest.raises(ValidationError, match="last_seen"):
        LogTemplate(
            cluster_id=1,
            template="x",
            size=1,
            sample_lines=["x"],
            first_seen=T_END,
            last_seen=T_START,
        )


def test_log_template_rejects_size_below_samples() -> None:
    """``size`` cannot be smaller than the number of sample lines kept."""
    with pytest.raises(ValidationError, match="size"):
        LogTemplate(
            cluster_id=1,
            template="x",
            size=1,
            sample_lines=["x", "y", "z"],
            first_seen=T_START,
            last_seen=T_END,
        )


def test_log_template_rejects_naive_datetime() -> None:
    """Naive datetimes are rejected to prevent silent tz-related bugs."""
    with pytest.raises(ValidationError):
        LogTemplate(
            cluster_id=1,
            template="x",
            size=1,
            sample_lines=["x"],
            first_seen=datetime(2026, 4, 18, 10, 0, 0),
            last_seen=datetime(2026, 4, 18, 11, 0, 0),
        )


# AggregatedTemplate ----------------------------------------------------------


def test_aggregated_template_valid(aggregated_template: AggregatedTemplate) -> None:
    """Happy path: composition preserves the nested template."""
    assert aggregated_template.total_count == 42
    assert aggregated_template.unique_ips == 3
    assert aggregated_template.template.cluster_id == 1


def test_aggregated_template_rejects_peak_below_mean(log_template: LogTemplate) -> None:
    """``peak_rate_per_minute`` must be >= ``rate_per_minute``."""
    with pytest.raises(ValidationError, match="peak_rate_per_minute"):
        AggregatedTemplate(
            template=log_template,
            total_count=10,
            rate_per_minute=2.0,
            peak_rate_per_minute=1.0,
            unique_ips=1,
            unique_users=1,
            sample_ips=["1.1.1.1"],
            sample_users=["root"],
        )


def test_aggregated_template_rejects_excess_ip_samples(log_template: LogTemplate) -> None:
    """Can't carry more sample IPs than the reported unique cardinality."""
    with pytest.raises(ValidationError, match="sample_ips"):
        AggregatedTemplate(
            template=log_template,
            total_count=10,
            rate_per_minute=1.0,
            peak_rate_per_minute=2.0,
            unique_ips=1,
            unique_users=1,
            sample_ips=["1.1.1.1", "2.2.2.2"],
            sample_users=["root"],
        )


def test_aggregated_template_rejects_malformed_ip(log_template: LogTemplate) -> None:
    """Malformed IP literals in ``sample_ips`` are rejected per-element."""
    with pytest.raises(ValidationError):
        AggregatedTemplate(
            template=log_template,
            total_count=10,
            rate_per_minute=1.0,
            peak_rate_per_minute=2.0,
            unique_ips=1,
            unique_users=1,
            sample_ips=["not-an-ip"],
            sample_users=["root"],
        )


def test_aggregated_template_accepts_ipv6_sample_ips(log_template: LogTemplate) -> None:
    """IPv6 literals (including IPv4-mapped) are valid ``sample_ips`` entries.

    The schema accepted IPv6 before the extractor did; this test pins
    that contract so a future validator tweak cannot regress it, and
    checks the literals are carried verbatim (no normalisation).
    """
    aggregated = AggregatedTemplate(
        template=log_template,
        total_count=10,
        rate_per_minute=1.0,
        peak_rate_per_minute=2.0,
        unique_ips=3,
        unique_users=1,
        sample_ips=["2001:db8::1", "::ffff:192.0.2.1", "fe80::1"],
        sample_users=["root"],
    )
    assert aggregated.sample_ips == ["2001:db8::1", "::ffff:192.0.2.1", "fe80::1"]


# FlaggedEvent ----------------------------------------------------------------


def test_flagged_event_valid(flagged_event: FlaggedEvent) -> None:
    """Happy path: enum decoded and score preserved."""
    assert flagged_event.score == pytest.approx(0.85)
    assert flagged_event.category is FlagCategory.BRUTE_FORCE


def test_flagged_event_rejects_score_above_one(
    aggregated_template: AggregatedTemplate,
) -> None:
    """Confidence score above 1.0 is rejected."""
    with pytest.raises(ValidationError, match="score"):
        FlaggedEvent(
            aggregated=aggregated_template,
            category=FlagCategory.NOVELTY,
            rule_name="first_seen_template",
            score=1.5,
            triggered_at=T_FLAGGED,
        )


def test_flagged_event_rejects_empty_rule_name(
    aggregated_template: AggregatedTemplate,
) -> None:
    """Empty ``rule_name`` fails the ``min_length`` constraint."""
    with pytest.raises(ValidationError, match="rule_name"):
        FlaggedEvent(
            aggregated=aggregated_template,
            category=FlagCategory.NOVELTY,
            rule_name="",
            score=0.5,
            triggered_at=T_FLAGGED,
        )


# ExplainedEvent --------------------------------------------------------------


def test_explained_event_valid(explained_event: ExplainedEvent) -> None:
    """Happy path: LLM metadata preserved end-to-end."""
    assert explained_event.severity is Severity.HIGH
    assert explained_event.llm_latency_ms == 1240
    assert explained_event.flagged.aggregated.template.cluster_id == 1


def test_explained_event_rejects_short_explanation(flagged_event: FlaggedEvent) -> None:
    """``explanation`` shorter than ``min_length`` is rejected."""
    with pytest.raises(ValidationError, match="explanation"):
        ExplainedEvent(
            flagged=flagged_event,
            explanation="short",
            severity=Severity.LOW,
            next_action="investigar o padrao",
            llm_model="m",
            llm_latency_ms=100,
            explained_at=T_EXPLAINED,
        )


def test_explained_event_rejects_negative_latency(flagged_event: FlaggedEvent) -> None:
    """Negative LLM latency is rejected by the ``ge=0`` constraint."""
    with pytest.raises(ValidationError, match="llm_latency_ms"):
        ExplainedEvent(
            flagged=flagged_event,
            explanation="A reasonably long explanation text.",
            severity=Severity.LOW,
            next_action="checar logs adjacentes",
            llm_model="m",
            llm_latency_ms=-1,
            explained_at=T_EXPLAINED,
        )


# Cross-cutting ---------------------------------------------------------------


def test_frozen_models_reject_mutation(log_template: LogTemplate) -> None:
    """``frozen=True`` must prevent field reassignment after construction."""
    target: Any = log_template
        with pytest.raises(ValidationError):
            log_template.size = 999


def test_explained_event_json_roundtrip(explained_event: ExplainedEvent) -> None:
    """``model_dump_json`` -> ``model_validate_json`` yields an equal object."""
    payload = explained_event.model_dump_json()
    restored = ExplainedEvent.model_validate_json(payload)
    assert restored == explained_event

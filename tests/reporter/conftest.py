"""Shared fixtures for Reporter tests.

The Reporter consumes ``ExplainedEvent`` instances, so the fixtures here
build them directly from schemas rather than going through the full
pipeline. A factory (:func:`make_explained`) is provided so individual
tests can override the fields that matter to them (severity, score,
template text) without repeating the full construction each time.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from lst.schemas import (
    AggregatedTemplate,
    ExplainedEvent,
    FlagCategory,
    FlaggedEvent,
    LogTemplate,
    Severity,
)

_DEFAULT_FIRST_SEEN = datetime(2026, 4, 18, 10, 0, 0, tzinfo=UTC)
_DEFAULT_LAST_SEEN = datetime(2026, 4, 18, 10, 30, 0, tzinfo=UTC)
_DEFAULT_EXPLAINED_AT = datetime(2026, 4, 18, 10, 35, 0, tzinfo=UTC)


@pytest.fixture
def make_explained() -> Callable[..., ExplainedEvent]:
    """Return a factory building :class:`ExplainedEvent` instances.

    All arguments are keyword-only and have sensible defaults, so each
    test can override just the fields under scrutiny. Defaults produce a
    high-severity brute-force event.
    """

    def _factory(
        *,
        cluster_id: int = 1,
        template: str = "Failed password for <*> from <*> port 22 ssh2",
        sample_lines: list[str] | None = None,
        total_count: int = 20,
        rate_per_minute: float = 0.67,
        peak_rate_per_minute: float = 2.0,
        unique_ips: int = 20,
        unique_users: int = 1,
        sample_ips: list[str] | None = None,
        sample_users: list[str] | None = None,
        category: FlagCategory = FlagCategory.BRUTE_FORCE,
        rule_name: str = "brute_force_by_ip_cardinality",
        score: float = 0.9,
        explanation: str = "Múltiplos IPs tentando autenticar contra o mesmo host.",
        severity: Severity = Severity.HIGH,
        next_action: str = "Bloquear os IPs ofensivos no firewall.",
        llm_model: str = "gpt-oss:120b",
        llm_latency_ms: int = 1200,
        first_seen: datetime = _DEFAULT_FIRST_SEEN,
        last_seen: datetime = _DEFAULT_LAST_SEEN,
        explained_at: datetime = _DEFAULT_EXPLAINED_AT,
    ) -> ExplainedEvent:
        default_samples = [
            "Failed password for root from 203.0.113.10 port 22 ssh2",
            "Failed password for root from 203.0.113.11 port 22 ssh2",
            "Failed password for root from 203.0.113.12 port 22 ssh2",
        ]
        default_ips = ["203.0.113.10", "203.0.113.11", "203.0.113.12"]
        default_users = ["root"]

        log_template = LogTemplate(
            cluster_id=cluster_id,
            template=template,
            size=min(total_count, 3),
            sample_lines=sample_lines if sample_lines is not None else default_samples,
            first_seen=first_seen,
            last_seen=last_seen,
        )
        aggregated = AggregatedTemplate(
            template=log_template,
            total_count=total_count,
            rate_per_minute=rate_per_minute,
            peak_rate_per_minute=peak_rate_per_minute,
            unique_ips=unique_ips,
            unique_users=unique_users,
            sample_ips=sample_ips if sample_ips is not None else default_ips,
            sample_users=sample_users if sample_users is not None else default_users,
        )
        flagged = FlaggedEvent(
            aggregated=aggregated,
            category=category,
            rule_name=rule_name,
            score=score,
            triggered_at=first_seen,
            context_notes=None,
        )
        return ExplainedEvent(
            flagged=flagged,
            explanation=explanation,
            severity=severity,
            next_action=next_action,
            llm_model=llm_model,
            llm_latency_ms=llm_latency_ms,
            explained_at=explained_at,
        )

    return _factory

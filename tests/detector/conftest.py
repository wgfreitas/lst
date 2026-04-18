"""Shared fixtures for Detector tests.

Exports a single factory -- :func:`make_aggregated` -- that builds a
valid :class:`AggregatedTemplate` from a small set of overrides. The
factory's job is to collapse the eight-field cross product of the
Pydantic model into the two or three fields each test actually cares
about, while auto-filling the Pydantic cross-field invariants
(``peak >= rate``, ``unique_ips >= len(sample_ips)``, and friends) so
tests don't rot when schema constraints tighten.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from lst.schemas import AggregatedTemplate, LogTemplate

_DEFAULT_FIRST_SEEN = datetime(2026, 4, 18, 10, 0, 0, tzinfo=UTC)


def _build_aggregated(
    *,
    cluster_id: int = 1,
    template: str = "benign template <*>",
    size: int | None = None,
    total_count: int = 1,
    rate_per_minute: float = 0.0,
    peak_rate_per_minute: float = 0.0,
    unique_ips: int | None = None,
    unique_users: int | None = None,
    sample_ips: list[str] | None = None,
    sample_users: list[str] | None = None,
    sample_lines: list[str] | None = None,
    first_seen: datetime | None = None,
    last_seen: datetime | None = None,
) -> AggregatedTemplate:
    """Return an ``AggregatedTemplate`` with invariants auto-patched."""
    ips = list(sample_ips) if sample_ips is not None else []
    users = list(sample_users) if sample_users is not None else []
    lines = list(sample_lines) if sample_lines is not None else ["placeholder sample"]
    first = first_seen or _DEFAULT_FIRST_SEEN
    last = last_seen or (first + timedelta(minutes=1))

    resolved_unique_ips = unique_ips if unique_ips is not None else len(ips)
    resolved_unique_users = unique_users if unique_users is not None else len(users)
    unique_ips_final = max(resolved_unique_ips, len(ips))
    unique_users_final = max(resolved_unique_users, len(users))

    resolved_size = size if size is not None else min(total_count, len(lines[:3]))
    resolved_size = max(resolved_size, 1)
    resolved_size = min(resolved_size, total_count)

    peak_final = max(peak_rate_per_minute, rate_per_minute)

    log_template = LogTemplate(
        cluster_id=cluster_id,
        template=template,
        size=resolved_size,
        sample_lines=lines[:3],
        first_seen=first,
        last_seen=last,
    )
    return AggregatedTemplate(
        template=log_template,
        total_count=total_count,
        rate_per_minute=rate_per_minute,
        peak_rate_per_minute=peak_final,
        unique_ips=unique_ips_final,
        unique_users=unique_users_final,
        sample_ips=ips[:5],
        sample_users=users[:5],
    )


@pytest.fixture
def make_aggregated() -> Callable[..., AggregatedTemplate]:
    """Return the :func:`_build_aggregated` factory (for test ergonomics)."""
    return _build_aggregated

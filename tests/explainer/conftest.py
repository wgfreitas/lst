"""Shared fixtures for Explainer tests.

Exports:

* :class:`FakeLLMClient` -- an in-memory implementation of
  :class:`~lst.explainer.client.LLMClient` that returns pre-queued
  replies or raises pre-queued exceptions. Used by the engine tests to
  avoid any HTTP-layer mocking at all.
* :func:`flagged_event_sample` -- a representative
  :class:`FlaggedEvent` matching the brute-force cluster in the static
  fixture. Constructed directly from schemas so explainer tests do not
  depend on Detector fixtures.
* :func:`settings_fixture` -- :class:`Settings` with ``_env_file=None``
  so tests never pick up a developer's local ``.env``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lst.config import Settings
from lst.schemas import (
    AggregatedTemplate,
    FlagCategory,
    FlaggedEvent,
    LogTemplate,
)


class FakeLLMClient:
    """Queue-based :class:`LLMClient` stand-in for engine tests.

    Each ``complete`` call pops the next item from ``responses``.
    ``str`` items are returned as the raw reply (paired with a
    monotonically increasing fake elapsed time); :class:`Exception`
    items are raised to simulate transport failures.
    """

    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses: list[str | Exception] = list(responses)
        self.calls: list[dict[str, object]] = []
        self._elapsed_ms = 41

    async def complete(
        self,
        system: str,
        user: str,
        *,
        model: str,
        timeout: float,
        json_mode: bool = True,
    ) -> tuple[str, int]:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "model": model,
                "timeout": timeout,
                "json_mode": json_mode,
            }
        )
        if not self.responses:
            raise RuntimeError("FakeLLMClient: no more responses queued")
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        self._elapsed_ms += 1
        return nxt, self._elapsed_ms


@pytest.fixture
def flagged_event_sample() -> FlaggedEvent:
    """A representative brute-force :class:`FlaggedEvent`."""
    first = datetime(2026, 4, 18, 10, 0, 1, tzinfo=UTC)
    last = datetime(2026, 4, 18, 10, 29, 55, tzinfo=UTC)
    template = LogTemplate(
        cluster_id=1,
        template="Failed password for <*> from <*> port 22 ssh2",
        size=20,
        sample_lines=[
            "Failed password for root from 203.0.113.10 port 22 ssh2",
            "Failed password for root from 203.0.113.15 port 22 ssh2",
            "Failed password for root from 203.0.113.29 port 22 ssh2",
        ],
        first_seen=first,
        last_seen=last,
    )
    aggregated = AggregatedTemplate(
        template=template,
        total_count=20,
        rate_per_minute=0.67,
        peak_rate_per_minute=2.0,
        unique_ips=20,
        unique_users=1,
        sample_ips=[
            "203.0.113.10",
            "203.0.113.11",
            "203.0.113.12",
            "203.0.113.13",
            "203.0.113.14",
        ],
        sample_users=["root"],
    )
    return FlaggedEvent(
        aggregated=aggregated,
        category=FlagCategory.BRUTE_FORCE,
        rule_name="brute_force_by_ip_cardinality",
        score=1.0,
        triggered_at=first,
        context_notes="20 distinct source IPs over 20 failed events (ratio=1.00)",
    )


@pytest.fixture
def settings_fixture() -> Settings:
    """Return a :class:`Settings` with ``_env_file=None`` to isolate tests."""
    return Settings(
        _env_file=None,
        llm_api_key="test-api-key",
        llm_model="test-model",
        llm_base_url="https://ollama.com/v1",
        llm_timeout_seconds=30.0,
        llm_max_retries=0,
        llm_max_tokens=1024,
    )

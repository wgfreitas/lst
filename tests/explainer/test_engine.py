"""Unit tests for :func:`lst.explainer.engine.explain`.

No HTTP machinery: every test injects a :class:`FakeLLMClient` with
queued responses, so failures are localised to the engine itself.
``explain`` returns ``(explained, discarded)`` and retries parse
failures up to ``parse_retries`` times before discarding an event.
"""

from __future__ import annotations

import logging

import pytest

from lst.explainer import explain
from lst.schemas import ExplainedEvent, FlaggedEvent, Severity
from tests.explainer.conftest import FakeLLMClient

_GOOD_RESPONSE = (
    '{"explanation": "Tentativa de brute force contra SSH.", '
    '"severity": "high", '
    '"next_action": "Bloquear os IPs ofensivos."}'
)
_SECOND_RESPONSE = (
    '{"explanation": "Conexão fechada por usuário inválido.", '
    '"severity": "medium", '
    '"next_action": "Investigar origem."}'
)
_BAD_RESPONSE = "not json at all"


async def test_explain_returns_explained_with_empty_discarded_in_order(
    flagged_event_sample: FlaggedEvent,
) -> None:
    """Two good events -> two explained, no discarded, order preserved."""
    second_event = flagged_event_sample.model_copy(update={"rule_name": "novelty_singleton"})
    fake = FakeLLMClient([_GOOD_RESPONSE, _SECOND_RESPONSE])

    explained, discarded = await explain(
        [flagged_event_sample, second_event],
        fake,
        model="test-model",
    )

    assert len(explained) == 2
    assert discarded == []
    assert all(isinstance(e, ExplainedEvent) for e in explained)
    assert explained[0].flagged.rule_name == "brute_force_by_ip_cardinality"
    assert explained[1].flagged.rule_name == "novelty_singleton"
    assert len(fake.calls) == 2


async def test_explain_populates_model_and_latency(
    flagged_event_sample: FlaggedEvent,
) -> None:
    """``llm_model`` and ``llm_latency_ms`` come from the invocation + client."""
    fake = FakeLLMClient([_GOOD_RESPONSE])
    explained, discarded = await explain([flagged_event_sample], fake, model="pinned-model")
    assert len(explained) == 1
    assert discarded == []
    assert explained[0].llm_model == "pinned-model"
    assert isinstance(explained[0].llm_latency_ms, int)
    assert explained[0].llm_latency_ms > 0


async def test_explain_returns_empty_for_empty_input() -> None:
    """No flagged events -> nothing explained, nothing discarded, no calls."""
    fake = FakeLLMClient([])
    explained, discarded = await explain([], fake, model="test-model")
    assert explained == []
    assert discarded == []
    assert fake.calls == []


async def test_explain_severity_is_parsed_into_enum(
    flagged_event_sample: FlaggedEvent,
) -> None:
    """The parsed severity string becomes a :class:`Severity` enum value."""
    fake = FakeLLMClient([_GOOD_RESPONSE])
    explained, _ = await explain([flagged_event_sample], fake, model="test-model")
    assert explained[0].severity is Severity.HIGH


async def test_explain_retries_parse_failure_then_succeeds(
    flagged_event_sample: FlaggedEvent,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Invalid reply on attempt 1, valid on attempt 2 -> explained (parse_retries=1)."""
    fake = FakeLLMClient([_BAD_RESPONSE, _GOOD_RESPONSE])
    with caplog.at_level(logging.WARNING):
        explained, discarded = await explain(
            [flagged_event_sample], fake, model="test-model", parse_retries=1
        )
    assert len(explained) == 1
    assert discarded == []
    assert len(fake.calls) == 2  # one retry consumed
    assert any("attempt 1/2 failed" in message for message in caplog.messages)


async def test_explain_discards_after_exhausting_retries(
    flagged_event_sample: FlaggedEvent,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Always-invalid replies -> event discarded after 1 + parse_retries attempts."""
    fake = FakeLLMClient([_BAD_RESPONSE, _BAD_RESPONSE])
    with caplog.at_level(logging.ERROR):
        explained, discarded = await explain(
            [flagged_event_sample], fake, model="test-model", parse_retries=1
        )
    assert explained == []
    assert discarded == [flagged_event_sample]
    assert len(fake.calls) == 2
    assert any("discarding" in message for message in caplog.messages)


async def test_explain_no_retry_when_parse_retries_zero(
    flagged_event_sample: FlaggedEvent,
) -> None:
    """parse_retries=0 -> a single attempt; the failure goes straight to discarded."""
    fake = FakeLLMClient([_BAD_RESPONSE])
    explained, discarded = await explain(
        [flagged_event_sample], fake, model="test-model", parse_retries=0
    )
    assert explained == []
    assert discarded == [flagged_event_sample]
    assert len(fake.calls) == 1


async def test_explain_discards_on_unknown_severity(
    flagged_event_sample: FlaggedEvent,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An out-of-enum severity is a parse failure: discarded, not raised."""
    bad_severity = (
        '{"explanation": "Explicação suficientemente longa para passar.", '
        '"severity": "urgent", "next_action": "Investigar o host."}'
    )
    fake = FakeLLMClient([bad_severity])
    with caplog.at_level(logging.WARNING):
        explained, discarded = await explain(
            [flagged_event_sample], fake, model="test-model", parse_retries=0
        )
    assert explained == []
    assert discarded == [flagged_event_sample]
    assert any("Severity" in message for message in caplog.messages)


async def test_explain_splits_mixed_batch_into_explained_and_discarded(
    flagged_event_sample: FlaggedEvent,
) -> None:
    """A batch with one good and one always-bad event splits correctly."""
    good_event = flagged_event_sample
    bad_event = flagged_event_sample.model_copy(update={"rule_name": "novelty_singleton"})
    # good_event: attempt 1 succeeds. bad_event: attempt 1 + retry both fail -> discarded.
    fake = FakeLLMClient([_GOOD_RESPONSE, _BAD_RESPONSE, _BAD_RESPONSE])

    explained, discarded = await explain(
        [good_event, bad_event], fake, model="test-model", parse_retries=1
    )

    assert len(explained) == 1
    assert explained[0].flagged.rule_name == "brute_force_by_ip_cardinality"
    assert discarded == [bad_event]
    assert len(fake.calls) == 3

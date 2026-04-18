"""Unit tests for :func:`lst.explainer.engine.explain`.

No HTTP machinery: every test injects a :class:`FakeLLMClient` with
queued responses, so failures are localised to the engine itself.
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


async def test_explain_returns_one_explained_per_event_in_order(
    flagged_event_sample: FlaggedEvent,
) -> None:
    """Two flagged events -> two explained events in the same order."""
    second_event = flagged_event_sample.model_copy(update={"rule_name": "novelty_singleton"})
    fake = FakeLLMClient([_GOOD_RESPONSE, _SECOND_RESPONSE])

    out = await explain(
        [flagged_event_sample, second_event],
        fake,
        model="test-model",
    )

    assert len(out) == 2
    assert all(isinstance(e, ExplainedEvent) for e in out)
    assert out[0].flagged.rule_name == "brute_force_by_ip_cardinality"
    assert out[1].flagged.rule_name == "novelty_singleton"
    assert len(fake.calls) == 2


async def test_explain_populates_model_and_latency(
    flagged_event_sample: FlaggedEvent,
) -> None:
    """``llm_model`` and ``llm_latency_ms`` come from the invocation + client."""
    fake = FakeLLMClient([_GOOD_RESPONSE])
    out = await explain([flagged_event_sample], fake, model="pinned-model")
    assert len(out) == 1
    assert out[0].llm_model == "pinned-model"
    assert isinstance(out[0].llm_latency_ms, int)
    assert out[0].llm_latency_ms > 0


async def test_explain_skips_malformed_response_and_keeps_valid(
    flagged_event_sample: FlaggedEvent,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A bad LLM reply is logged at ERROR and the event is dropped, not raised."""
    second_event = flagged_event_sample.model_copy(update={"rule_name": "novelty_singleton"})
    fake = FakeLLMClient(["not json at all", _GOOD_RESPONSE])
    with caplog.at_level(logging.ERROR):
        out = await explain(
            [flagged_event_sample, second_event],
            fake,
            model="test-model",
        )
    assert len(out) == 1
    assert out[0].flagged.rule_name == "novelty_singleton"
    assert any("unparseable" in message for message in caplog.messages)


async def test_explain_skips_when_severity_outside_enum(
    flagged_event_sample: FlaggedEvent,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A made-up severity ('urgent') is logged and the event dropped."""
    bad_severity = '{"explanation": "x", "severity": "urgent", "next_action": "y"}'
    fake = FakeLLMClient([bad_severity])
    with caplog.at_level(logging.ERROR):
        out = await explain([flagged_event_sample], fake, model="test-model")
    assert out == []
    assert any("severity" in msg for msg in caplog.messages)


async def test_explain_returns_empty_for_empty_input() -> None:
    """No flagged events -> no explained events, no client calls."""
    fake = FakeLLMClient([])
    out = await explain([], fake, model="test-model")
    assert out == []
    assert fake.calls == []


async def test_explain_severity_is_parsed_into_enum(
    flagged_event_sample: FlaggedEvent,
) -> None:
    """The parsed severity string becomes a :class:`Severity` enum value."""
    fake = FakeLLMClient([_GOOD_RESPONSE])
    out = await explain([flagged_event_sample], fake, model="test-model")
    assert out[0].severity is Severity.HIGH

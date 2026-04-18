"""Unit tests for :mod:`lst.explainer.prompt`."""

from __future__ import annotations

import pytest

from lst.explainer.prompt import build_messages
from lst.schemas import FlaggedEvent


@pytest.fixture
def messages(flagged_event_sample: FlaggedEvent) -> tuple[str, str]:
    return build_messages(flagged_event_sample)


def test_system_prompt_names_expected_json_fields(messages: tuple[str, str]) -> None:
    """System prompt must name each field the parser will later extract."""
    system_prompt, _ = messages
    assert "JSON" in system_prompt
    assert "explanation" in system_prompt
    assert "severity" in system_prompt
    assert "next_action" in system_prompt


def test_user_prompt_includes_template_score_and_counts(
    messages: tuple[str, str],
    flagged_event_sample: FlaggedEvent,
) -> None:
    """User prompt carries the core FlaggedEvent fields verbatim."""
    _, user_prompt = messages
    assert flagged_event_sample.aggregated.template.template in user_prompt
    assert f"{flagged_event_sample.score:.2f}" in user_prompt
    assert str(flagged_event_sample.aggregated.total_count) in user_prompt
    assert flagged_event_sample.rule_name in user_prompt


def test_user_prompt_caps_ip_sample_at_three(
    messages: tuple[str, str],
    flagged_event_sample: FlaggedEvent,
) -> None:
    """Only the first three IPs from ``sample_ips`` should appear in the prompt."""
    _, user_prompt = messages
    first_three = flagged_event_sample.aggregated.sample_ips[:3]
    for literal in first_three:
        assert literal in user_prompt
    dropped = flagged_event_sample.aggregated.sample_ips[3:]
    for literal in dropped:
        assert literal not in user_prompt


def test_user_prompt_renders_missing_context_notes_as_placeholder(
    flagged_event_sample: FlaggedEvent,
) -> None:
    """``context_notes=None`` must render as the literal '(nenhuma)'."""
    stripped = flagged_event_sample.model_copy(update={"context_notes": None})
    _, user_prompt = build_messages(stripped)
    assert "(nenhuma)" in user_prompt


def test_user_prompt_numbers_sample_lines(
    messages: tuple[str, str],
    flagged_event_sample: FlaggedEvent,
) -> None:
    """Each sample_line appears on its own numbered entry (1., 2., ...)."""
    _, user_prompt = messages
    samples = flagged_event_sample.aggregated.template.sample_lines
    for index, raw_line in enumerate(samples, start=1):
        assert f"{index}. {raw_line}" in user_prompt

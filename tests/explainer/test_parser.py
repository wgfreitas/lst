"""Unit tests for :mod:`lst.explainer.parser`."""

from __future__ import annotations

import pytest

from lst.explainer.parser import parse_response


def test_parse_response_returns_dict_on_clean_json() -> None:
    """A well-formed JSON object is parsed directly."""
    raw = (
        '{"explanation": "Tentativa de brute force.", '
        '"severity": "high", '
        '"next_action": "Bloquear IPs ofensivos."}'
    )
    parsed = parse_response(raw)
    assert parsed == {
        "explanation": "Tentativa de brute force.",
        "severity": "high",
        "next_action": "Bloquear IPs ofensivos.",
    }


def test_parse_response_strips_markdown_json_fence() -> None:
    """``\\`\\`\\`json ... \\`\\`\\``` wrappers are removed before decoding."""
    raw = (
        "```json\n"
        '{"explanation": "Explicação.", "severity": "medium", '
        '"next_action": "Rever logs."}\n'
        "```"
    )
    parsed = parse_response(raw)
    assert parsed["severity"] == "medium"


def test_parse_response_tolerates_leading_text() -> None:
    """Extra prose before the JSON body is ignored via the regex fallback."""
    raw = (
        "Aqui está o JSON solicitado:\n"
        '{"explanation": "ok", "severity": "low", "next_action": "nada."}'
    )
    parsed = parse_response(raw)
    assert parsed["explanation"] == "ok"


def test_parse_response_raises_for_malformed_json() -> None:
    """Garbled text with no extractable JSON body raises ``ValueError``."""
    with pytest.raises(ValueError, match="no JSON object"):
        parse_response("not json at all, no braces")


def test_parse_response_raises_when_required_field_missing() -> None:
    """A valid object without all three required keys is rejected."""
    raw = '{"explanation": "x", "severity": "low"}'
    with pytest.raises(ValueError, match="missing required fields"):
        parse_response(raw)


def test_parse_response_lowercases_severity() -> None:
    """``severity`` is normalised so downstream ``StrEnum`` works."""
    raw = '{"explanation": "x", "severity": "HIGH", "next_action": "y"}'
    parsed = parse_response(raw)
    assert parsed["severity"] == "high"


def test_parse_response_extracts_outermost_object_when_nested() -> None:
    """A creative model that nests objects still yields a valid top-level dict."""
    raw = (
        '{"explanation": "indica algo", "severity": "medium", '
        '"next_action": "investigar", "extra": {"trace": "ignored"}}'
    )
    parsed = parse_response(raw)
    assert parsed["explanation"] == "indica algo"
    assert "extra" not in parsed


def test_parse_response_strips_field_whitespace() -> None:
    """Leading/trailing whitespace in string fields is trimmed."""
    raw = '{"explanation": "  espaços  ", "severity": "  LOW  ", "next_action": " ação "}'
    parsed = parse_response(raw)
    assert parsed["explanation"] == "espaços"
    assert parsed["severity"] == "low"
    assert parsed["next_action"] == "ação"

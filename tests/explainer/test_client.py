"""Unit tests for :class:`lst.explainer.client.OpenAICompatClient`.

Every test stubs the ``chat.completions.create`` HTTP path via
:mod:`respx` -- no real network traffic is permitted. The structured-
output strategy is pinned per test (via the ``auto`` default or
:func:`_settings_with_mode`) so the cascade
``json_schema -> json_object -> none`` is deterministic, and request
bodies are decoded to assert which ``response_format`` actually went out.
"""

from __future__ import annotations

import json
from typing import Literal

import httpx
import pytest
import respx
from openai import APITimeoutError, AuthenticationError, BadRequestError

from lst.config import Settings
from lst.explainer.client import _RESPONSE_JSON_SCHEMA, OpenAICompatClient

_ENDPOINT = "https://ollama.com/v1/chat/completions"
_GOOD = '{"explanation":"ok","severity":"low","next_action":"x"}'
_JSON_OBJECT_FORMAT = {"type": "json_object"}

_StructuredMode = Literal["auto", "json_schema", "json_object", "none"]


def _settings_with_mode(mode: _StructuredMode) -> Settings:
    """Build isolated :class:`Settings` with a pinned structured-output mode."""
    return Settings(
        _env_file=None,
        llm_api_key="test-api-key",
        llm_model="test-model",
        llm_base_url="https://ollama.com/v1",
        llm_timeout_seconds=30.0,
        llm_max_retries=0,
        llm_max_tokens=1024,
        llm_structured_mode=mode,
    )


def _chat_response_payload(content: str) -> dict[str, object]:
    """Return a minimal OpenAI-style chat.completions body."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


def _bad_request(message: str) -> httpx.Response:
    """A 400 response whose error message carries ``message``."""
    return httpx.Response(
        400,
        json={"error": {"message": message, "type": "invalid_request_error"}},
    )


def _sent_body(route: respx.Route, index: int) -> dict[str, object]:
    """Decode the JSON body of the ``index``-th captured request."""
    decoded: dict[str, object] = json.loads(route.calls[index].request.content.decode("utf-8"))
    return decoded


# --------------------------------------------------------------------------- #
# Cascade behaviour
# --------------------------------------------------------------------------- #
async def test_auto_uses_json_schema_when_accepted(settings_fixture: Settings) -> None:
    """``auto`` sends strict json_schema first and stops when it is accepted."""
    payload = _chat_response_payload(_GOOD)
    with respx.mock(assert_all_called=True) as router:
        route = router.post(_ENDPOINT).mock(return_value=httpx.Response(200, json=payload))
        client = OpenAICompatClient(settings_fixture)
        content, elapsed = await client.complete("system", "user", model="test-model", timeout=5.0)
        assert route.call_count == 1
        sent = _sent_body(route, 0)
    assert sent["response_format"] == _RESPONSE_JSON_SCHEMA
    assert content.startswith("{")
    assert elapsed >= 0


async def test_auto_degrades_to_json_object_when_json_schema_rejected(
    settings_fixture: Settings,
) -> None:
    """A json_schema rejection steps the cascade down to json_object."""
    good = _chat_response_payload(_GOOD)
    with respx.mock(assert_all_called=True) as router:
        route = router.post(_ENDPOINT).mock(
            side_effect=[
                _bad_request("json_schema response_format is not supported by this model"),
                httpx.Response(200, json=good),
            ]
        )
        client = OpenAICompatClient(settings_fixture)
        content, _ = await client.complete("system", "user", model="test-model", timeout=5.0)
        assert route.call_count == 2
        first, second = _sent_body(route, 0), _sent_body(route, 1)
    assert first["response_format"] == _RESPONSE_JSON_SCHEMA
    assert second["response_format"] == _JSON_OBJECT_FORMAT
    assert "explanation" in content


async def test_auto_degrades_to_none_when_schema_and_object_rejected(
    settings_fixture: Settings,
) -> None:
    """Two rejections drop the cascade all the way to free text (no response_format)."""
    good = _chat_response_payload(_GOOD)
    with respx.mock(assert_all_called=True) as router:
        route = router.post(_ENDPOINT).mock(
            side_effect=[
                _bad_request("json_schema is not supported"),
                _bad_request("response_format json_object is not supported"),
                httpx.Response(200, json=good),
            ]
        )
        client = OpenAICompatClient(settings_fixture)
        content, _ = await client.complete("system", "user", model="test-model", timeout=5.0)
        assert route.call_count == 3
        third = _sent_body(route, 2)
    assert "response_format" not in third
    assert third["max_tokens"] == 1024
    assert "explanation" in content


async def test_auto_unrelated_bad_request_propagates_without_degrading(
    settings_fixture: Settings,
) -> None:
    """A 400 unrelated to response_format is raised immediately, not degraded."""
    with respx.mock(assert_all_called=True) as router:
        route = router.post(_ENDPOINT).mock(return_value=_bad_request("model 'x' not found"))
        client = OpenAICompatClient(settings_fixture)
        with pytest.raises(BadRequestError):
            await client.complete("system", "user", model="test-model", timeout=5.0)
        assert route.call_count == 1


async def test_explicit_json_schema_propagates_rejection() -> None:
    """A pinned json_schema mode does not degrade: the rejection propagates."""
    with respx.mock(assert_all_called=True) as router:
        route = router.post(_ENDPOINT).mock(return_value=_bad_request("json_schema not supported"))
        client = OpenAICompatClient(_settings_with_mode("json_schema"))
        with pytest.raises(BadRequestError):
            await client.complete("system", "user", model="test-model", timeout=5.0)
        assert route.call_count == 1


async def test_none_mode_omits_response_format() -> None:
    """A pinned ``none`` mode never sends a response_format field."""
    good = _chat_response_payload(_GOOD)
    with respx.mock(assert_all_called=True) as router:
        route = router.post(_ENDPOINT).mock(return_value=httpx.Response(200, json=good))
        client = OpenAICompatClient(_settings_with_mode("none"))
        await client.complete("system", "user", model="test-model", timeout=5.0)
        assert route.call_count == 1
        sent = _sent_body(route, 0)
    assert "response_format" not in sent
    assert sent["max_tokens"] == 1024


async def test_json_object_mode_sends_object_format_and_max_tokens() -> None:
    """A pinned json_object mode carries ``{"type": "json_object"}`` + max_tokens."""
    payload = _chat_response_payload(_GOOD)
    with respx.mock(assert_all_called=True) as router:
        route = router.post(_ENDPOINT).mock(return_value=httpx.Response(200, json=payload))
        client = OpenAICompatClient(_settings_with_mode("json_object"))
        await client.complete("system", "user", model="test-model", timeout=5.0)
        sent = _sent_body(route, 0)
    assert sent["response_format"] == _JSON_OBJECT_FORMAT
    assert sent["max_tokens"] == 1024


# --------------------------------------------------------------------------- #
# Transport errors propagate through the cascade unchanged
# --------------------------------------------------------------------------- #
async def test_complete_propagates_timeout(settings_fixture: Settings) -> None:
    """Transport timeouts bubble up wrapped as :class:`openai.APITimeoutError`."""
    with respx.mock(assert_all_called=True) as router:
        router.post(_ENDPOINT).mock(side_effect=httpx.TimeoutException("slow"))
        client = OpenAICompatClient(settings_fixture)
        with pytest.raises(APITimeoutError):
            await client.complete("system", "user", model="test-model", timeout=0.01)


async def test_complete_raises_on_authentication_error(settings_fixture: Settings) -> None:
    """A 401 surfaces as :class:`openai.AuthenticationError`, no degradation."""
    body = {"error": {"message": "invalid api key", "type": "authentication_error"}}
    with respx.mock(assert_all_called=True) as router:
        router.post(_ENDPOINT).mock(return_value=httpx.Response(401, json=body))
        client = OpenAICompatClient(settings_fixture)
        with pytest.raises(AuthenticationError):
            await client.complete("system", "user", model="test-model", timeout=5.0)


async def test_complete_elapsed_is_int(settings_fixture: Settings) -> None:
    """``elapsed_ms`` is always a non-negative int, never a float."""
    payload = _chat_response_payload(_GOOD)
    with respx.mock(assert_all_called=True) as router:
        router.post(_ENDPOINT).mock(return_value=httpx.Response(200, json=payload))
        client = OpenAICompatClient(settings_fixture)
        _, elapsed = await client.complete("system", "user", model="test-model", timeout=5.0)
    assert isinstance(elapsed, int)
    assert elapsed >= 0

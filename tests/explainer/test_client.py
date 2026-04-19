"""Unit tests for :class:`lst.explainer.client.OllamaClient`.

Every test stubs the ``chat.completions.create`` HTTP path via
:mod:`respx` -- no real network traffic is permitted. The respx route
assertion at the end of each test guards against accidental bypass
(which could happen if the SDK changes its base URL or routing).
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from openai import APITimeoutError, AuthenticationError

from lst.config import Settings
from lst.explainer.client import OllamaClient

_ENDPOINT = "https://ollama.com/v1/chat/completions"


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


async def test_complete_happy_path_returns_content_and_elapsed(
    settings_fixture: Settings,
) -> None:
    """A 200 response surfaces content + a non-negative elapsed time."""
    payload = _chat_response_payload('{"explanation":"ok","severity":"low","next_action":"x"}')
    with respx.mock(assert_all_called=True) as router:
        route = router.post(_ENDPOINT).mock(return_value=httpx.Response(200, json=payload))
        client = OllamaClient(settings_fixture)
        content, elapsed = await client.complete(
            "system",
            "user",
            model="test-model",
            timeout=5.0,
        )
        assert route.called
        assert route.call_count == 1
    assert content.startswith("{")
    assert elapsed >= 0


async def test_complete_falls_back_when_json_mode_rejected(
    settings_fixture: Settings,
) -> None:
    """A 400 naming ``response_format`` triggers a retry without json mode."""
    bad_request = httpx.Response(
        400,
        json={
            "error": {
                "message": "response_format json_object is not supported by this model",
                "type": "invalid_request_error",
            }
        },
    )
    good_payload = _chat_response_payload('{"explanation":"a","severity":"low","next_action":"b"}')
    with respx.mock(assert_all_called=True) as router:
        route = router.post(_ENDPOINT).mock(
            side_effect=[bad_request, httpx.Response(200, json=good_payload)]
        )
        client = OllamaClient(settings_fixture)
        content, _ = await client.complete(
            "system",
            "user",
            model="test-model",
            timeout=5.0,
        )
        assert route.call_count == 2
    assert "explanation" in content


async def test_complete_propagates_timeout(settings_fixture: Settings) -> None:
    """Transport timeouts bubble up wrapped as :class:`openai.APITimeoutError`."""
    with respx.mock(assert_all_called=True) as router:
        router.post(_ENDPOINT).mock(side_effect=httpx.TimeoutException("slow"))
        client = OllamaClient(settings_fixture)
        with pytest.raises(APITimeoutError):
            await client.complete(
                "system",
                "user",
                model="test-model",
                timeout=0.01,
            )


async def test_complete_raises_on_authentication_error(
    settings_fixture: Settings,
) -> None:
    """A 401 surfaces as :class:`openai.AuthenticationError`."""
    body = {"error": {"message": "invalid api key", "type": "authentication_error"}}
    with respx.mock(assert_all_called=True) as router:
        router.post(_ENDPOINT).mock(return_value=httpx.Response(401, json=body))
        client = OllamaClient(settings_fixture)
        with pytest.raises(AuthenticationError):
            await client.complete(
                "system",
                "user",
                model="test-model",
                timeout=5.0,
            )


async def test_complete_elapsed_is_int(settings_fixture: Settings) -> None:
    """``elapsed_ms`` is always a non-negative int, never a float."""
    payload = _chat_response_payload('{"explanation":"a","severity":"low","next_action":"b"}')
    with respx.mock(assert_all_called=True) as router:
        router.post(_ENDPOINT).mock(return_value=httpx.Response(200, json=payload))
        client = OllamaClient(settings_fixture)
        _, elapsed = await client.complete(
            "system",
            "user",
            model="test-model",
            timeout=5.0,
        )
    assert isinstance(elapsed, int)
    assert elapsed >= 0


async def test_complete_includes_max_tokens_in_payload(
    settings_fixture: Settings,
) -> None:
    """``max_tokens`` from settings is serialised into the outbound request."""
    payload = _chat_response_payload('{"explanation":"a","severity":"low","next_action":"b"}')
    with respx.mock(assert_all_called=True) as router:
        route = router.post(_ENDPOINT).mock(return_value=httpx.Response(200, json=payload))
        client = OllamaClient(settings_fixture)
        await client.complete(
            "system",
            "user",
            model="test-model",
            timeout=5.0,
            json_mode=True,
        )
        sent = json.loads(route.calls[0].request.content.decode("utf-8"))
    assert sent["max_tokens"] == settings_fixture.llm_max_tokens
    assert sent["response_format"] == {"type": "json_object"}


async def test_complete_fallback_also_includes_max_tokens(
    settings_fixture: Settings,
) -> None:
    """The json-mode fallback retry also carries ``max_tokens``."""
    bad_request = httpx.Response(
        400,
        json={
            "error": {
                "message": "response_format json_object is not supported by this model",
                "type": "invalid_request_error",
            }
        },
    )
    good_payload = _chat_response_payload('{"explanation":"a","severity":"low","next_action":"b"}')
    with respx.mock(assert_all_called=True) as router:
        route = router.post(_ENDPOINT).mock(
            side_effect=[bad_request, httpx.Response(200, json=good_payload)]
        )
        client = OllamaClient(settings_fixture)
        await client.complete(
            "system",
            "user",
            model="test-model",
            timeout=5.0,
        )
        assert route.call_count == 2
        retry_payload = json.loads(route.calls[1].request.content.decode("utf-8"))
    assert retry_payload["max_tokens"] == settings_fixture.llm_max_tokens
    assert "response_format" not in retry_payload

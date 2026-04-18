"""Async HTTP client for the Ollama Cloud chat-completions endpoint.

The Explainer talks to Ollama Cloud through the OpenAI-compatible REST
API, reusing the official ``openai`` SDK. Going through the SDK buys
us retries with exponential back-off, HTTP error taxonomy, and the
(still-moving) authentication flow -- all of which would be tedious
and error-prone to reproduce with raw :mod:`httpx` calls.

Two layers live here:

* :class:`LLMClient` -- the :class:`typing.Protocol` every orchestrator
  depends on. Describing the contract independently of the concrete
  class is what lets the engine tests inject a fake client without
  touching :mod:`respx` or HTTP machinery.
* :class:`OllamaClient` -- the production implementation. It pins
  :class:`AsyncOpenAI` to the Ollama Cloud base URL, falls back to a
  JSON-mode-less retry when the model rejects
  ``response_format=json_object``, and measures wall-clock latency
  with :func:`time.monotonic` so the :class:`ExplainedEvent`'s
  ``llm_latency_ms`` field reflects the actual round-trip, not a mock.
"""

from __future__ import annotations

import time
from typing import Protocol

from openai import AsyncOpenAI, BadRequestError
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from lst.config import Settings

_JSON_MODE_HINT = "response_format"


class LLMClient(Protocol):
    """Protocol implemented by any async client the Explainer can drive.

    The Protocol deliberately returns the raw response text rather than
    a parsed dict -- parsing lives in :mod:`lst.explainer.parser` so
    callers can log the bytes the model actually produced before
    deciding what to do with them.
    """

    async def complete(
        self,
        system: str,
        user: str,
        *,
        model: str,
        timeout: float,
        json_mode: bool = True,
    ) -> tuple[str, int]:
        """Send one chat-completion request and return ``(text, elapsed_ms)``.

        Args:
            system: Content of the ``system`` message.
            user: Content of the ``user`` message.
            model: Model identifier understood by the remote endpoint.
            timeout: Per-request wall-clock budget, in seconds.
            json_mode: Whether to hint the endpoint to emit JSON via
                ``response_format``. Implementations must transparently
                retry without the hint when the model rejects it.

        Returns:
            A 2-tuple ``(text, elapsed_ms)``: the raw response content
            and the integer round-trip latency in milliseconds.
        """
        ...


class OllamaClient:
    """Concrete :class:`LLMClient` backed by ``openai.AsyncOpenAI``.

    The underlying :class:`AsyncOpenAI` instance is created once per
    :class:`OllamaClient` and reused across requests -- the SDK keeps a
    pooled :class:`httpx.AsyncClient` internally, so each ``complete``
    call is a single HTTP round-trip, not a fresh connection.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialise the client from a :class:`Settings` snapshot."""
        self._client = AsyncOpenAI(
            base_url=settings.ollama_base_url,
            api_key=settings.ollama_api_key,
            max_retries=settings.llm_max_retries,
        )
        self._default_timeout = settings.llm_timeout_seconds

    async def complete(
        self,
        system: str,
        user: str,
        *,
        model: str,
        timeout: float,
        json_mode: bool = True,
    ) -> tuple[str, int]:
        """Run one chat-completion call, with JSON-mode fallback on rejection."""
        started = time.monotonic()
        try:
            response = await self._request(
                system=system,
                user=user,
                model=model,
                timeout=timeout,
                json_mode=json_mode,
            )
        except BadRequestError as exc:
            if json_mode and _JSON_MODE_HINT in str(exc).lower():
                response = await self._request(
                    system=system,
                    user=user,
                    model=model,
                    timeout=timeout,
                    json_mode=False,
                )
            else:
                raise

        elapsed_ms = int((time.monotonic() - started) * 1000)
        content = response.choices[0].message.content or ""
        return content, elapsed_ms

    async def _request(
        self,
        *,
        system: str,
        user: str,
        model: str,
        timeout: float,
        json_mode: bool,
    ) -> ChatCompletion:
        """Single chat-completion round-trip. Isolated for the json-mode retry."""
        messages: list[ChatCompletionSystemMessageParam | ChatCompletionUserMessageParam] = [
            ChatCompletionSystemMessageParam(role="system", content=system),
            ChatCompletionUserMessageParam(role="user", content=user),
        ]
        if json_mode:
            return await self._client.chat.completions.create(
                model=model,
                messages=messages,
                timeout=timeout,
                response_format={"type": "json_object"},
            )
        return await self._client.chat.completions.create(
            model=model,
            messages=messages,
            timeout=timeout,
        )

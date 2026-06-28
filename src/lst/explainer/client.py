"""Async HTTP client for OpenAI-compatible chat-completions endpoints.

The Explainer talks to its LLM provider through the OpenAI-compatible
REST API, reusing the official ``openai`` SDK. Going through the SDK buys
us retries with exponential back-off, HTTP error taxonomy, and the
(still-moving) authentication flow -- all of which would be tedious and
error-prone to reproduce with raw :mod:`httpx` calls. Any provider that
exposes an OpenAI-compatible ``/chat/completions`` endpoint works without
code changes -- Ollama Cloud (the default), GLM (Z.ai), OpenRouter, or
OpenAI itself -- since only the base URL, API key, and model name differ.

Structured output is the fragile part of that contract: providers disagree
on which ``response_format`` they accept. The client resolves this with a
**degradation cascade** driven by :attr:`Settings.llm_structured_mode`:

* ``json_schema`` -- strict JSON Schema (``strict: True``,
  ``additionalProperties: False``, all three fields required). This is the
  sturdiest option: it forces the required fields at the API layer, which
  eliminates the truncated-reply failure mode seen on some providers.
* ``json_object`` -- the looser ``{"type": "json_object"}`` hint.
* ``none`` -- no ``response_format`` at all; trust the prompt + parser.

In ``auto`` mode the client tries those three in order and steps down one
level each time the provider answers with a ``response_format``-related
:class:`openai.BadRequestError`. It never parses the error string to guess
*which* knob failed -- error wording varies by provider, so sequential
degradation is the robust strategy. Pinning the mode (``json_schema`` /
``json_object`` / ``none``) disables the cascade and propagates the error.

Two layers live here:

* :class:`LLMClient` -- the :class:`typing.Protocol` every orchestrator
  depends on. Describing the contract independently of the concrete
  class is what lets the engine tests inject a fake client without
  touching :mod:`respx` or HTTP machinery.
* :class:`OpenAICompatClient` -- the production implementation. It pins
  :class:`AsyncOpenAI` to the configured base URL, runs the structured-
  output cascade, and measures wall-clock latency with
  :func:`time.monotonic` so the :class:`ExplainedEvent`'s
  ``llm_latency_ms`` field reflects the actual round-trip, not a mock.
"""

from __future__ import annotations

import logging
import time
from typing import Literal, Protocol

from openai import AsyncOpenAI, BadRequestError
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.shared_params import ResponseFormatJSONSchema

from lst.config import Settings

logger = logging.getLogger(__name__)

# Concrete request modes the cascade can emit (``auto`` is a strategy, not a
# request mode -- it expands to the full sequence below).
_RequestMode = Literal["json_schema", "json_object", "none"]

# Strict JSON Schema for the triage reply. ``strict``/``additionalProperties``
# force the three required fields at the API layer, which is what stops a
# provider from streaming back a truncated object missing ``severity`` or
# ``next_action``. Typed as ``ResponseFormatJSONSchema`` so the openai SDK's
# overloaded ``create`` accepts it under mypy --strict.
_RESPONSE_JSON_SCHEMA: ResponseFormatJSONSchema = {
    "type": "json_schema",
    "json_schema": {
        "name": "triage_explanation",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "explanation": {"type": "string"},
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                },
                "next_action": {"type": "string"},
            },
            "required": ["explanation", "severity", "next_action"],
            "additionalProperties": False,
        },
    },
}

# Substrings (case-insensitive) that mark a BadRequestError as a
# ``response_format`` rejection worth degrading on, rather than a genuine
# request error (bad model name, etc.) that must propagate. ``json_schema``
# is listed explicitly for readability even though ``schema`` subsumes it.
_RESPONSE_FORMAT_MARKERS: tuple[str, ...] = ("response_format", "json_schema", "schema")

# Expand each configured strategy into the ordered request modes to attempt.
_MODE_CASCADE: dict[str, tuple[_RequestMode, ...]] = {
    "auto": ("json_schema", "json_object", "none"),
    "json_schema": ("json_schema",),
    "json_object": ("json_object",),
    "none": ("none",),
}


def _is_response_format_rejection(exc: BadRequestError) -> bool:
    """Return ``True`` if ``exc`` looks like a ``response_format`` rejection."""
    message = str(exc).lower()
    return any(marker in message for marker in _RESPONSE_FORMAT_MARKERS)


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
            json_mode: Legacy hint kept for contract compatibility. The
                production client now derives its structured-output
                strategy from :attr:`Settings.llm_structured_mode` and
                ignores this flag; fakes may still honour it.

        Returns:
            A 2-tuple ``(text, elapsed_ms)``: the raw response content
            and the integer round-trip latency in milliseconds.
        """
        ...


class OpenAICompatClient:
    """Concrete :class:`LLMClient` backed by ``openai.AsyncOpenAI``.

    The underlying :class:`AsyncOpenAI` instance is created once per
    :class:`OpenAICompatClient` and reused across requests -- the SDK
    keeps a pooled :class:`httpx.AsyncClient` internally, so each
    ``complete`` call is a single HTTP round-trip per cascade step, not a
    fresh connection. The base URL, API key, retry budget, and
    structured-output strategy all come from :class:`Settings`, so
    pointing at a different OpenAI-compatible provider is purely a
    configuration change.
    """

    def __init__(self, settings: Settings) -> None:
        """Initialise the client from a :class:`Settings` snapshot."""
        self._client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            max_retries=settings.llm_max_retries,
        )
        self._default_timeout = settings.llm_timeout_seconds
        self._max_tokens = settings.llm_max_tokens
        self._structured_mode = settings.llm_structured_mode

    async def complete(
        self,
        system: str,
        user: str,
        *,
        model: str,
        timeout: float,
        json_mode: bool = True,
    ) -> tuple[str, int]:
        """Run one chat-completion call through the structured-output cascade.

        Walks the request modes implied by
        :attr:`Settings.llm_structured_mode`, degrading one level on each
        ``response_format``-related :class:`openai.BadRequestError`. A
        rejection unrelated to ``response_format`` (or any non-400 error)
        propagates immediately. ``json_mode`` is accepted for Protocol
        compatibility but ignored.
        """
        started = time.monotonic()
        last_error: BadRequestError | None = None
        for mode in _MODE_CASCADE[self._structured_mode]:
            try:
                response = await self._request(
                    system=system,
                    user=user,
                    model=model,
                    timeout=timeout,
                    mode=mode,
                )
            except BadRequestError as exc:
                if not _is_response_format_rejection(exc):
                    raise
                logger.warning("Provider rejected structured-output mode '%s'; degrading", mode)
                last_error = exc
                continue

            elapsed_ms = int((time.monotonic() - started) * 1000)
            content = response.choices[0].message.content or ""
            return content, elapsed_ms

        # Cascade exhausted: every mode was rejected for response_format.
        if last_error is not None:
            raise last_error
        raise RuntimeError("no structured-output mode configured")  # pragma: no cover

    async def _request(
        self,
        *,
        system: str,
        user: str,
        model: str,
        timeout: float,
        mode: _RequestMode,
    ) -> ChatCompletion:
        """Single chat-completion round-trip for one structured-output mode."""
        messages: list[ChatCompletionSystemMessageParam | ChatCompletionUserMessageParam] = [
            ChatCompletionSystemMessageParam(role="system", content=system),
            ChatCompletionUserMessageParam(role="user", content=user),
        ]
        if mode == "json_schema":
            return await self._client.chat.completions.create(
                model=model,
                messages=messages,
                timeout=timeout,
                max_tokens=self._max_tokens,
                response_format=_RESPONSE_JSON_SCHEMA,
            )
        if mode == "json_object":
            return await self._client.chat.completions.create(
                model=model,
                messages=messages,
                timeout=timeout,
                max_tokens=self._max_tokens,
                response_format={"type": "json_object"},
            )
        return await self._client.chat.completions.create(
            model=model,
            messages=messages,
            timeout=timeout,
            max_tokens=self._max_tokens,
        )

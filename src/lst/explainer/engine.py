"""Orchestrate Explainer runs: flagged events in, explained + discarded out.

The engine wires the three narrow pieces of the Explainer stage
together:

* :func:`lst.explainer.prompt.build_messages` -- derive ``(system,
  user)`` from a :class:`FlaggedEvent`.
* :class:`lst.explainer.client.LLMClient` -- ship the messages to a
  remote model, return raw text plus latency.
* :func:`lst.explainer.parser.parse_response` -- turn the raw text into
  a three-field dict suitable for :class:`ExplainedEvent`.

Policy decisions encoded here:

* **Order preservation** -- the returned ``explained`` list is aligned
  with the input by index for the events that succeed. Failures are not
  padded with ``None``; they are collected separately so the Reporter
  sees a strictly shorter list of explained events plus an explicit list
  of the ones it must flag as un-analysed.
* **Retry then discard on malformed response** -- structured output can
  still come back empty or truncated under a ``200 OK`` (the ``openai``
  library only retries genuine HTTP errors). Each event is attempted up
  to ``1 + parse_retries`` times; a parse failure, an unknown severity,
  or a reply that fails :class:`ExplainedEvent` validation is logged at
  ``WARNING`` and retried. If every attempt fails the event is logged at
  ``ERROR`` and returned in the ``discarded`` list so the Reporter can
  surface it honestly instead of dropping it silently.
* **Re-raise on infrastructure errors** -- auth failures, connection
  errors, and timeouts are re-raised by the client and propagate through
  here. These signal a misconfigured or unreachable endpoint; pretending
  to succeed with partial data would be worse than failing fast.
* **Sequential** by design -- the MVP processes events one at a time.
  Parallelism is cheap to add with :func:`asyncio.gather` later, but
  it complicates rate-limit handling and introduces output-ordering
  questions that are not worth the cost right now.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from lst.explainer.client import LLMClient
from lst.explainer.parser import parse_response
from lst.explainer.prompt import build_messages
from lst.schemas import ExplainedEvent, FlaggedEvent, Severity

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 60.0
_DEFAULT_PARSE_RETRIES = 1


async def explain(
    events: list[FlaggedEvent],
    client: LLMClient,
    *,
    model: str,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    parse_retries: int = _DEFAULT_PARSE_RETRIES,
) -> tuple[list[ExplainedEvent], list[FlaggedEvent]]:
    """Enrich each :class:`FlaggedEvent` with an LLM analysis.

    Args:
        events: Flagged events produced by the Detector stage.
        client: Any object satisfying :class:`LLMClient`. The production
            CLI passes :class:`~lst.explainer.client.OpenAICompatClient`;
            tests inject a fake.
        model: Model identifier forwarded verbatim to the client.
        timeout: Per-request wall-clock budget handed to
            :meth:`LLMClient.complete`. Defaults to 60s.
        parse_retries: Extra attempts to re-request and parse a reply that
            comes back empty or unparseable. ``parse_retries=1`` (default)
            means at most two attempts per event. Covers the ``200 OK``
            but empty/truncated reply that the HTTP-level retry misses.

    Returns:
        A 2-tuple ``(explained, discarded)``. ``explained`` holds one
        :class:`ExplainedEvent` per successfully-analysed event, in input
        order. ``discarded`` holds the :class:`FlaggedEvent` instances
        that could not be explained after every attempt, in input order.
    """
    explained: list[ExplainedEvent] = []
    discarded: list[FlaggedEvent] = []
    for event in events:
        result = await _explain_one(
            event,
            client,
            model=model,
            timeout=timeout,
            parse_retries=parse_retries,
        )
        if result is None:
            discarded.append(event)
        else:
            explained.append(result)

    return explained, discarded


async def _explain_one(
    event: FlaggedEvent,
    client: LLMClient,
    *,
    model: str,
    timeout: float,
    parse_retries: int,
) -> ExplainedEvent | None:
    """Explain one event, retrying parse failures. ``None`` if all attempts fail."""
    system_prompt, user_prompt = build_messages(event)
    cluster_id = event.aggregated.template.cluster_id
    attempts = parse_retries + 1

    for attempt in range(1, attempts + 1):
        content, elapsed_ms = await client.complete(
            system_prompt,
            user_prompt,
            model=model,
            timeout=timeout,
        )
        try:
            return _build_explained(event, content=content, model=model, elapsed_ms=elapsed_ms)
        except ValueError as exc:
            # ValueError covers the parser, an out-of-enum severity, and
            # ExplainedEvent model validation (pydantic ValidationError is a
            # ValueError subclass) -- every "200 OK but unusable" failure mode.
            logger.warning(
                "Explainer attempt %d/%d failed for cluster_id=%s: %s; raw=%r",
                attempt,
                attempts,
                cluster_id,
                exc,
                content,
            )

    logger.error(
        "Explainer discarding cluster_id=%s after %d attempt(s): no valid response",
        cluster_id,
        attempts,
    )
    return None


def _build_explained(
    event: FlaggedEvent,
    *,
    content: str,
    model: str,
    elapsed_ms: int,
) -> ExplainedEvent:
    """Turn one raw reply into an :class:`ExplainedEvent`.

    Raises:
        ValueError: if the reply cannot be parsed, carries a severity
            outside :class:`Severity`, or fails :class:`ExplainedEvent`
            validation (``pydantic.ValidationError`` subclasses
            ``ValueError``).
    """
    parsed = parse_response(content)
    severity = Severity(parsed["severity"])
    return ExplainedEvent(
        flagged=event,
        explanation=parsed["explanation"],
        severity=severity,
        next_action=parsed["next_action"],
        llm_model=model,
        llm_latency_ms=elapsed_ms,
        explained_at=datetime.now(UTC),
    )

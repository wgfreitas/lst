"""Orchestrate Explainer runs: flagged events in, explained events out.

The engine wires the three narrow pieces of the Explainer stage
together:

* :func:`lst.explainer.prompt.build_messages` -- derive ``(system,
  user)`` from a :class:`FlaggedEvent`.
* :class:`lst.explainer.client.LLMClient` -- ship the messages to a
  remote model, return raw text plus latency.
* :func:`lst.explainer.parser.parse_response` -- turn the raw text into
  a three-field dict suitable for :class:`ExplainedEvent`.

Policy decisions encoded here:

* **Order preservation** -- the returned list is aligned with the
  input by index when all events succeed. Failures are skipped rather
  than padded, so the Reporter sees a strictly shorter list, never a
  list with ``None`` placeholders.
* **Skip on malformed response** -- if the LLM returns text that the
  parser rejects, the event is dropped with an ``ERROR`` log entry
  carrying the ``cluster_id`` and the raw reply. Rationale: a single
  bad response should not truncate an otherwise-good run.
* **Re-raise on infrastructure errors** -- auth failures, connection
  errors, and timeouts are re-raised. These signal a misconfigured or
  unreachable endpoint; pretending to succeed with partial data would
  be worse than failing fast.
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


async def explain(
    events: list[FlaggedEvent],
    client: LLMClient,
    *,
    model: str,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
) -> list[ExplainedEvent]:
    """Enrich each :class:`FlaggedEvent` with an LLM analysis.

    Args:
        events: Flagged events produced by the Detector stage.
        client: Any object satisfying :class:`LLMClient`. The production
            CLI passes :class:`~lst.explainer.client.OpenAICompatClient`;
            tests inject a fake.
        model: Model identifier forwarded verbatim to the client.
        timeout: Per-request wall-clock budget handed to
            :meth:`LLMClient.complete`. Defaults to 60s.

    Returns:
        A list of :class:`ExplainedEvent`, in the same order as
        ``events``. Events whose LLM reply cannot be parsed are logged
        at ``ERROR`` and omitted from the result.
    """
    explained: list[ExplainedEvent] = []
    for event in events:
        system_prompt, user_prompt = build_messages(event)

        content, elapsed_ms = await client.complete(
            system_prompt,
            user_prompt,
            model=model,
            timeout=timeout,
        )

        try:
            parsed = parse_response(content)
        except ValueError as exc:
            logger.error(
                "LLM response unparseable for cluster_id=%s: %s; raw=%r",
                event.aggregated.template.cluster_id,
                exc,
                content,
            )
            continue

        try:
            severity = Severity(parsed["severity"])
        except ValueError:
            logger.error(
                "LLM returned unknown severity=%r for cluster_id=%s",
                parsed["severity"],
                event.aggregated.template.cluster_id,
            )
            continue

        explained.append(
            ExplainedEvent(
                flagged=event,
                explanation=parsed["explanation"],
                severity=severity,
                next_action=parsed["next_action"],
                llm_model=model,
                llm_latency_ms=elapsed_ms,
                explained_at=datetime.now(UTC),
            )
        )

    return explained

"""LLM Explainer stage: enrich flagged events with pt-BR analysis.

The Detector emits deterministic :class:`FlaggedEvent` records; the
Explainer asks an LLM (Ollama Cloud via the OpenAI-compatible endpoint)
to turn each flag into a triage-ready :class:`ExplainedEvent` carrying
an explanation, a severity, and a next-action recommendation -- all in
Brazilian Portuguese.

Architecture (one concern per file):

* :mod:`lst.explainer.client` -- thin async wrapper over the OpenAI
  client library, with a :class:`Protocol` so tests can swap in a fake.
* :mod:`lst.explainer.prompt` -- pure ``FlaggedEvent -> (system, user)``
  message builder.
* :mod:`lst.explainer.parser` -- pure ``str -> dict`` response parser,
  tolerant of markdown fences and stray text around the JSON body.
* :mod:`lst.explainer.engine` -- the single public entry point,
  :func:`explain`, which orchestrates the three pieces above.

This is the only stage in the pipeline that performs network I/O.
"""

from lst.explainer.engine import explain

__all__ = ["explain"]

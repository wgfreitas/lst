"""Detector stage: apply deterministic rules over aggregated templates.

Consumes a ``list[AggregatedTemplate]`` from the Aggregator and returns
a ``list[FlaggedEvent]`` -- the input set the LLM Explainer works on.

Public surface:

* :func:`detect` -- the stage's single entry point.
* :mod:`lst.detector.rules` -- the rule registry, one module per rule.
"""

from lst.detector.engine import detect

__all__ = ["detect"]

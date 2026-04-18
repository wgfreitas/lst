"""Aggregator stage: enrich each template with window-level statistics.

Consumes the pair ``(list[LogTemplate], list[MinedLine])`` produced by
the Parser stage and returns a ``list[AggregatedTemplate]`` with rates,
peaks, cardinalities, and representative IPs/users ready for the
Detector stage.

Public surface:

* :func:`aggregate` -- the stage's single entry point.
* :mod:`lst.aggregator.extractors` -- the stateless IP/user extractors,
  reusable by the Parser and the Detector.
"""

from lst.aggregator.stats import aggregate

__all__ = ["aggregate"]

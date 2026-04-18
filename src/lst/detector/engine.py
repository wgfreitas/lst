"""Detector engine: run all active rules, dedup, and sort.

The engine owns three concerns so rules can stay narrow:

1. **Orchestration** -- call ``rule.evaluate(aggregated)`` for every
   ``(rule, aggregated)`` pair. Rules are pure, so this loop is trivially
   parallelisable if throughput ever becomes a bottleneck (not now).
2. **Deduplication** -- at most one :class:`FlaggedEvent` is emitted per
   ``cluster_id``. When several rules fire on the same cluster we keep
   the event with the highest ``(score, category_priority)`` tuple.
   ``score`` dominates; the priority table only settles ties.
3. **Ordering** -- final output is sorted by the same ``(score,
   priority)`` key in descending order, so the most actionable event
   reaches the Explainer first. Ordering is deterministic -- given the
   same input, two runs produce identical output.

Priority table (used only to break score ties, never to override it):

    BRUTE_FORCE       5
    HIGH_RISK_PATTERN 4
    NOVELTY           3
    SPIKE             2
    VARIETY           1

Rationale: when two rules report equal confidence, the more specific
classification wins. BruteForce is the most surgical finding; Variety
is the least specific catch-all.
"""

from __future__ import annotations

from lst.detector.rules import ACTIVE_RULES
from lst.detector.rules.base import Rule
from lst.schemas import AggregatedTemplate, FlagCategory, FlaggedEvent

_CATEGORY_PRIORITY: dict[FlagCategory, int] = {
    FlagCategory.BRUTE_FORCE: 5,
    FlagCategory.HIGH_RISK_PATTERN: 4,
    FlagCategory.NOVELTY: 3,
    FlagCategory.SPIKE: 2,
    FlagCategory.VARIETY: 1,
}


def _pick_key(event: FlaggedEvent) -> tuple[float, int]:
    """Return the ``(score, priority)`` sort key for an event.

    Priority only matters on score ties -- a 0.81 BRUTE_FORCE still
    loses to a 0.82 NOVELTY.
    """
    return (event.score, _CATEGORY_PRIORITY[event.category])


def detect(
    aggregated: list[AggregatedTemplate],
    *,
    rules: list[Rule] | None = None,
) -> list[FlaggedEvent]:
    """Run the deterministic rule set over an aggregated batch.

    Args:
        aggregated: Per-cluster aggregates emitted by
            :func:`lst.aggregator.aggregate`. An empty list yields an
            empty result -- the engine is total over its input.
        rules: Rule set to run. Defaults to :data:`ACTIVE_RULES`; the
            parameter is exposed for tests that want to pin a
            single-rule scenario.

    Returns:
        Flagged events sorted by ``(score, category_priority)``
        descending, with at most one event per ``cluster_id``.
    """
    active_rules = ACTIVE_RULES if rules is None else rules

    best_per_cluster: dict[int, FlaggedEvent] = {}
    for template in aggregated:
        for rule in active_rules:
            event = rule.evaluate(template)
            if event is None:
                continue
            cluster_id = event.aggregated.template.cluster_id
            incumbent = best_per_cluster.get(cluster_id)
            if incumbent is None or _pick_key(event) > _pick_key(incumbent):
                best_per_cluster[cluster_id] = event

    return sorted(best_per_cluster.values(), key=_pick_key, reverse=True)

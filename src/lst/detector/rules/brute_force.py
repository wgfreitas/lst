"""BruteForceRule -- many distinct source IPs failing against one template.

The classical SSH brute-force fingerprint: a single template (e.g.
``Failed password for <*> from <*> port <*>``) triggered by at least
:data:`_MIN_UNIQUE_IPS` distinct source IPs, where the vast majority of
rows (:data:`_MIN_IP_RATIO`) carry a unique IP, and the template itself
looks like a failure (:data:`FAIL_VERBS_RE`).

The failure-verb gate exists to suppress benign fan-ins -- a load
balancer health check naturally spans hundreds of IPs but should not
fire this rule.
"""

from __future__ import annotations

from datetime import UTC, datetime

from lst.detector.rules.patterns import FAIL_VERBS_RE
from lst.schemas import AggregatedTemplate, FlagCategory, FlaggedEvent

_MIN_UNIQUE_IPS = 10
_MIN_IP_RATIO = 0.8
_SCORE_SATURATION_IPS = 20.0


class BruteForceRule:
    """Flag IP-diverse failure bursts against a single template."""

    name: str = "brute_force_by_ip_cardinality"
    category: FlagCategory = FlagCategory.BRUTE_FORCE
    description_pt: str = "muitos IPs distintos contra padrão de falha"

    def evaluate(self, aggregated: AggregatedTemplate) -> FlaggedEvent | None:
        """Fire on IP-diverse, failure-verbed templates."""
        if aggregated.unique_ips < _MIN_UNIQUE_IPS:
            return None
        if aggregated.total_count == 0:
            return None
        ip_ratio = aggregated.unique_ips / aggregated.total_count
        if ip_ratio < _MIN_IP_RATIO:
            return None
        if FAIL_VERBS_RE.search(aggregated.template.template) is None:
            return None

        score = min(1.0, aggregated.unique_ips / _SCORE_SATURATION_IPS)
        notes = (
            f"{aggregated.unique_ips} distinct source IPs over "
            f"{aggregated.total_count} failed events "
            f"(ratio={ip_ratio:.2f})"
        )
        return FlaggedEvent(
            aggregated=aggregated,
            category=self.category,
            rule_name=self.name,
            score=score,
            triggered_at=datetime.now(UTC),
            context_notes=notes,
        )

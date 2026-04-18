"""VarietyRule -- IP fan-in with no auth verb to classify.

Catches clusters where many distinct IPs hit the same template but the
template itself carries neither a failure verb (which would make it a
BruteForce candidate) nor a success verb (which would make it benign
auth traffic). These tend to be scans, probes, or misrouted traffic
against a single endpoint -- worth surfacing but lower-priority than
brute-force.
"""

from __future__ import annotations

from datetime import UTC, datetime

from lst.detector.rules.patterns import FAIL_VERBS_RE, SUCCESS_VERBS_RE
from lst.schemas import AggregatedTemplate, FlagCategory, FlaggedEvent

_MIN_UNIQUE_IPS = 5
_MIN_IP_RATIO = 0.5
_SCORE_SATURATION_IPS = 30.0


class VarietyRule:
    """Flag IP-diverse templates with no explicit auth classification."""

    name: str = "source_variety_no_auth_context"
    category: FlagCategory = FlagCategory.VARIETY

    def evaluate(self, aggregated: AggregatedTemplate) -> FlaggedEvent | None:
        """Fire on IP-diverse templates lacking success/fail verbs."""
        if aggregated.unique_ips < _MIN_UNIQUE_IPS:
            return None
        if aggregated.total_count == 0:
            return None
        ip_ratio = aggregated.unique_ips / aggregated.total_count
        if ip_ratio < _MIN_IP_RATIO:
            return None

        template_text = aggregated.template.template
        if SUCCESS_VERBS_RE.search(template_text) is not None:
            return None
        if FAIL_VERBS_RE.search(template_text) is not None:
            return None

        score = min(1.0, aggregated.unique_ips / _SCORE_SATURATION_IPS)
        notes = (
            f"{aggregated.unique_ips} distinct IPs on "
            f"{aggregated.total_count} events with no auth verb "
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

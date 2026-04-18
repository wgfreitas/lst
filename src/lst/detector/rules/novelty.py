"""NoveltyRule -- a template seen exactly once in the window.

Templates with ``total_count == 1`` are the long tail of log traffic and
are, empirically, where the interesting oddities live: a first-time
``POSSIBLE BREAK-IN ATTEMPT``, a lone ``sudo: NOT in sudoers`` entry, a
single kernel-level alert. The rule assigns a base score of 0.6 and
boosts to 0.9 when the template text contains a high-risk keyword
(:data:`HIGH_RISK_PATTERNS`), so reports sort the alarming singletons
above the merely-rare ones.
"""

from __future__ import annotations

from datetime import UTC, datetime

from lst.detector.rules.patterns import HIGH_RISK_PATTERNS
from lst.schemas import AggregatedTemplate, FlagCategory, FlaggedEvent

_BASE_SCORE = 0.6
_BOOSTED_SCORE = 0.9


class NoveltyRule:
    """Flag one-off templates, boosting score on high-risk phrasing."""

    name: str = "novelty_singleton"
    category: FlagCategory = FlagCategory.NOVELTY
    description_pt: str = "templates vistos apenas uma vez na janela"

    def evaluate(self, aggregated: AggregatedTemplate) -> FlaggedEvent | None:
        """Fire when the cluster has exactly one matched line."""
        if aggregated.total_count != 1:
            return None

        template_text = aggregated.template.template
        matched_keyword: str | None = None
        for keyword_name, pattern in HIGH_RISK_PATTERNS:
            if pattern.search(template_text):
                matched_keyword = keyword_name
                break

        score = _BOOSTED_SCORE if matched_keyword is not None else _BASE_SCORE
        if matched_keyword is not None:
            notes = f"singleton template with high-risk keyword: {matched_keyword}"
        else:
            notes = "singleton template (total_count=1)"

        return FlaggedEvent(
            aggregated=aggregated,
            category=self.category,
            rule_name=self.name,
            score=score,
            triggered_at=datetime.now(UTC),
            context_notes=notes,
        )

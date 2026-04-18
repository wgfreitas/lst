"""HighRiskPatternRule -- literal IOC / alarm phrasing hits.

Matches the template text (preferred) or any of the retained
``sample_lines`` (fallback) against :data:`HIGH_RISK_PATTERNS`. Unlike
NoveltyRule, frequency does not matter -- one ``kernel panic`` should
fire, and so should a thousand of them; the Explainer will decide what
to recommend.

The fixed score of 0.8 signals "high-confidence deterministic hit". The
engine's tie-break means that when this rule fires on the same cluster
as a higher-priority rule (e.g. brute-force), the higher-priority rule
wins and the analyst still sees the event -- just categorised as the
more specific class.
"""

from __future__ import annotations

from datetime import UTC, datetime

from lst.detector.rules.patterns import HIGH_RISK_PATTERNS
from lst.schemas import AggregatedTemplate, FlagCategory, FlaggedEvent

_SCORE = 0.8


class HighRiskPatternRule:
    """Flag templates or samples containing known high-risk keywords."""

    name: str = "high_risk_keyword_match"
    category: FlagCategory = FlagCategory.HIGH_RISK_PATTERN
    description_pt: str = "padrões conhecidos de alto risco (IOCs/alertas)"

    def evaluate(self, aggregated: AggregatedTemplate) -> FlaggedEvent | None:
        """Fire when template or any sample line matches a known IOC."""
        template_text = aggregated.template.template
        for keyword_name, pattern in HIGH_RISK_PATTERNS:
            if pattern.search(template_text):
                return self._build(aggregated, keyword_name, "template")

        for sample in aggregated.template.sample_lines:
            for keyword_name, pattern in HIGH_RISK_PATTERNS:
                if pattern.search(sample):
                    return self._build(aggregated, keyword_name, "sample_lines")

        return None

    def _build(
        self,
        aggregated: AggregatedTemplate,
        keyword_name: str,
        source: str,
    ) -> FlaggedEvent:
        return FlaggedEvent(
            aggregated=aggregated,
            category=self.category,
            rule_name=self.name,
            score=_SCORE,
            triggered_at=datetime.now(UTC),
            context_notes=f"high-risk keyword '{keyword_name}' matched in {source}",
        )

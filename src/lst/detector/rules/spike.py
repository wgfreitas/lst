"""SpikeRule -- anomalous bursts relative to the cluster's mean rate.

Two triggers, either one is enough when ``total_count >=
_MIN_TOTAL_FOR_SPIKE``:

* **Absolute** -- ``peak_rate_per_minute >= _ABSOLUTE_PEAK``. Five events
  in a single minute on one template is a lot for the kinds of log
  sources this CLI targets (auth, kernel, firewall).
* **Relative** -- ``peak_rate_per_minute >= rate_per_minute * _MULTIPLIER``
  **and** ``peak_rate_per_minute >= _RELATIVE_MIN_PEAK``. The extra
  floor on the relative arm matters because very-rare clusters trivially
  produce huge ratios (e.g. rate 0.25/min, peak 1/min is ``4x`` the
  mean but only one event) and those are not spikes, they are ordinary
  low-volume noise.

The score blends absolute and relative information by dividing peak by
the mean rate (with ``rate=0`` guarded to ``1.0``) and normalising by 10
so a 10x spike saturates the score at 1.0.
"""

from __future__ import annotations

from datetime import UTC, datetime

from lst.schemas import AggregatedTemplate, FlagCategory, FlaggedEvent

_ABSOLUTE_PEAK = 5.0
_MULTIPLIER = 3.0
_RELATIVE_MIN_PEAK = 3.0
_MIN_TOTAL_FOR_SPIKE = 3
_SCORE_SATURATION_RATIO = 10.0


class SpikeRule:
    """Flag clusters whose peak minute dwarfs their mean rate."""

    name: str = "rate_spike_3sigma_or_absolute"
    category: FlagCategory = FlagCategory.SPIKE
    description_pt: str = "picos anormais de taxa vs. média da janela"

    def evaluate(self, aggregated: AggregatedTemplate) -> FlaggedEvent | None:
        """Fire on absolute or relative rate spikes with enough events."""
        if aggregated.total_count < _MIN_TOTAL_FOR_SPIKE:
            return None

        peak = aggregated.peak_rate_per_minute
        rate = aggregated.rate_per_minute
        absolute_trigger = peak >= _ABSOLUTE_PEAK
        relative_trigger = (peak >= rate * _MULTIPLIER) and (peak >= _RELATIVE_MIN_PEAK)
        if not (absolute_trigger or relative_trigger):
            return None

        divisor = rate if rate > 0 else 1.0
        score = min(1.0, peak / divisor / _SCORE_SATURATION_RATIO)
        notes = f"peak={peak:.2f}/min over mean={rate:.2f}/min (ratio={(peak / divisor):.2f}x)"
        return FlaggedEvent(
            aggregated=aggregated,
            category=self.category,
            rule_name=self.name,
            score=score,
            triggered_at=datetime.now(UTC),
            context_notes=notes,
        )

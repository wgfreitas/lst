"""Aggregator core: compute window statistics per template.

Groups :class:`~lst.parser.MinedLine` rows by ``cluster_id`` and, for
each template, derives:

* ``total_count`` -- number of lines in the cluster.
* ``rate_per_minute`` -- mean events per minute across
  ``[first_seen, last_seen]``, floored to one minute to avoid division
  by zero for bursty clusters.
* ``peak_rate_per_minute`` -- max events in a single tumbling 1-minute
  bucket. Clamped up to ``rate_per_minute`` so the schema invariant
  ``peak >= rate`` holds for narrow-span bursts.
* ``unique_ips`` / ``unique_users`` -- cardinalities of the extracted
  tokens, deduplicated in first-seen order.
* ``sample_ips`` / ``sample_users`` -- up to five representatives each.

Each aggregation step is pulled into a small private helper so the
formulas are inspectable in isolation (ETIR analysts like being able
to read one function at a time).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from ipaddress import ip_address

from lst.parser._mined_line import MinedLine
from lst.schemas import AggregatedTemplate, LogTemplate

logger = logging.getLogger(__name__)

_SAMPLE_LIMIT = 5


def aggregate(
    templates: list[LogTemplate],
    lines: list[MinedLine],
) -> list[AggregatedTemplate]:
    """Enrich each template with window-level statistics.

    The output preserves the input ``templates`` order so downstream
    stages can rely on positional correspondence when useful.

    Args:
        templates: Templates emitted by the Parser stage.
        lines: Per-line DTOs produced alongside the templates. Must be
            a superset of every ``cluster_id`` appearing in
            ``templates`` -- a missing cluster is treated as an upstream
            bug (the Parser would have emitted a template without any
            supporting line data).

    Returns:
        One :class:`AggregatedTemplate` per input template, in input order.

    Raises:
        ValueError: if any template has no matching :class:`MinedLine`.
    """
    grouped: defaultdict[int, list[MinedLine]] = defaultdict(list)
    for line in lines:
        grouped[line.cluster_id].append(line)

    result: list[AggregatedTemplate] = []
    for template in templates:
        cluster_lines = grouped.get(template.cluster_id)
        if not cluster_lines:
            message = (
                f"no MinedLine rows matched cluster_id={template.cluster_id}; "
                "upstream Parser/drain3 inconsistency"
            )
            logger.warning(message)
            raise ValueError(message)

        total_count = len(cluster_lines)
        rate, peak = _compute_rates(cluster_lines, total_count)
        unique_ips_ordered = _dedupe_ips(cluster_lines)
        unique_users_ordered = _dedupe_users(cluster_lines)

        result.append(
            AggregatedTemplate(
                template=template,
                total_count=total_count,
                rate_per_minute=rate,
                peak_rate_per_minute=peak,
                unique_ips=len(unique_ips_ordered),
                unique_users=len(unique_users_ordered),
                sample_ips=unique_ips_ordered[:_SAMPLE_LIMIT],
                sample_users=unique_users_ordered[:_SAMPLE_LIMIT],
            )
        )
    return result


def _compute_rates(
    cluster_lines: list[MinedLine],
    total_count: int,
) -> tuple[float, float]:
    """Return ``(rate_per_minute, peak_rate_per_minute)`` for a cluster.

    ``rate`` uses the span between first and last timestamp, floored to
    one minute so a one-line cluster or an identical-timestamp cluster
    still produces a finite value. ``peak`` is the maximum count in any
    single tumbling 1-minute bucket keyed on ``(year, month, day, hour,
    minute)``. For narrow-span bursts (e.g. 20 events in 30 seconds)
    ``rate`` can numerically exceed ``peak`` after flooring; we clamp
    ``peak`` up so the schema invariant ``peak >= rate`` always holds.
    """
    timestamps = [line.timestamp for line in cluster_lines]
    first, last = min(timestamps), max(timestamps)
    span_minutes = (last - first).total_seconds() / 60.0
    rate = total_count / max(1.0, span_minutes)

    buckets: defaultdict[tuple[int, int, int, int, int], int] = defaultdict(int)
    for timestamp in timestamps:
        key = (
            timestamp.year,
            timestamp.month,
            timestamp.day,
            timestamp.hour,
            timestamp.minute,
        )
        buckets[key] += 1
    peak = float(max(buckets.values()))

    return rate, max(peak, rate)


def _dedupe_ips(cluster_lines: list[MinedLine]) -> list[str]:
    """Return IPs deduplicated in first-seen order, re-validated defensively."""
    seen: set[str] = set()
    ordered: list[str] = []
    for line in cluster_lines:
        for candidate in line.extracted_ips:
            if candidate in seen:
                continue
            try:
                ip_address(candidate)
            except ValueError:  # pragma: no cover
                # MinedLine already validated on construction; this branch
                # only fires if the upstream validator is relaxed later.
                continue
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


def _dedupe_users(cluster_lines: list[MinedLine]) -> list[str]:
    """Return usernames deduplicated in first-seen order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for line in cluster_lines:
        for candidate in line.extracted_users:
            if candidate in seen:
                continue
            seen.add(candidate)
            ordered.append(candidate)
    return ordered

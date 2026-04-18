"""Wrap drain3 to produce ``LogTemplate`` aggregates.

Adds three concerns on top of the raw drain3 streaming API:

1. Per-line timestamp extraction -- ISO-8601 and RFC-3164 syslog prefixes
   are recognised. Lines without a parseable timestamp fall back to
   ``datetime.now(UTC)`` so the downstream ``LogTemplate`` model can still
   be built.
2. Structured-prefix stripping -- the syslog ``Mon DD HH:MM:SS host
   proc[PID]:`` preamble is removed before the line is fed to drain3.
   Otherwise hostnames and PIDs leak into templates and inflate the
   cluster count.
3. Per-cluster sample bookkeeping -- for each cluster we keep the first
   line, a periodically-refreshed middle line (every other time ``size``
   is even), and the latest line. That caps sample memory at three lines
   per cluster while still reflecting drift over a long stream.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

from lst.aggregator.extractors import extract_ips, extract_users
from lst.parser._mined_line import MinedLine
from lst.schemas import LogTemplate

_ISO_TS = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}" r"(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)

_SYSLOG_MONTHS: dict[str, int] = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

_SYSLOG_TS = re.compile(
    r"^(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"\s+(?P<day>\d{1,2})\s+(?P<time>\d{2}:\d{2}:\d{2})"
)

_SYSLOG_PREFIX = re.compile(
    r"^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}"
    r"\s+\S+\s+[^:\s]+?(?:\[\d+\])?:\s*"
)


def _extract_timestamp(line: str) -> datetime | None:
    """Return the first timestamp on ``line``, or ``None`` if absent.

    Recognises ISO-8601 (naive values are promoted to UTC rather than
    left ambiguous) and RFC-3164 syslog (``Mon DD HH:MM:SS``). Syslog
    carries no year, so the current UTC year is assumed -- fine during
    steady-state analysis, slightly off for December/January crossings.
    """
    iso_match = _ISO_TS.match(line)
    if iso_match is not None:
        normalised = iso_match.group("ts").replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalised)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    syslog_match = _SYSLOG_TS.match(line)
    if syslog_match is not None:
        time_token = syslog_match.group("time")
        try:
            return datetime(
                year=datetime.now(UTC).year,
                month=_SYSLOG_MONTHS[syslog_match.group("month")],
                day=int(syslog_match.group("day")),
                hour=int(time_token[0:2]),
                minute=int(time_token[3:5]),
                second=int(time_token[6:8]),
                tzinfo=UTC,
            )
        except ValueError:
            return None

    return None


def _strip_structured_prefix(line: str) -> str:
    """Remove a syslog RFC-3164 prefix if present.

    Hostnames and ``proc[PID]`` tokens would otherwise leak into drain3
    templates and explode the cluster vocabulary. Lines without a
    recognised prefix are returned unchanged.
    """
    return _SYSLOG_PREFIX.sub("", line, count=1)


@dataclass
class _TemplateAccumulator:
    """Running state for one drain3 cluster across a single stream."""

    cluster_id: int
    first_sample: str | None = None
    middle_sample: str | None = None
    last_sample: str | None = None
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    size: int = 0

    def update(self, raw_line: str, timestamp: datetime) -> None:
        """Record one more line hitting this cluster."""
        self.size += 1
        if self.first_seen is None or timestamp < self.first_seen:
            self.first_seen = timestamp
        if self.last_seen is None or timestamp > self.last_seen:
            self.last_seen = timestamp
        if self.first_sample is None:
            self.first_sample = raw_line
        elif self.size % 2 == 0:
            self.middle_sample = raw_line
        self.last_sample = raw_line

    def samples(self) -> list[str]:
        """Up to three representative raw lines, de-duplicated, in order."""
        seen: set[str] = set()
        ordered: list[str] = []
        for candidate in (self.first_sample, self.middle_sample, self.last_sample):
            if candidate is None or candidate in seen:
                continue
            seen.add(candidate)
            ordered.append(candidate)
        return ordered[:3]


def _make_config(sim_th: float, depth: int, max_clusters: int) -> TemplateMinerConfig:
    """Build a drain3 config with our defaults applied."""
    config = TemplateMinerConfig()
    config.drain_sim_th = sim_th
    config.drain_depth = depth
    config.drain_max_clusters = max_clusters
    config.parametrize_numeric_tokens = True
    config.snapshot_interval_minutes = 0
    config.profiling_enabled = False
    return config


def mine_templates(
    lines: Iterable[str],
    *,
    sim_th: float = 0.4,
    depth: int = 4,
    max_clusters: int = 1024,
) -> tuple[list[LogTemplate], list[MinedLine]]:
    """Cluster ``lines`` with drain3 and return templates + per-line DTOs.

    The input is consumed lazily, so pairing this with
    :func:`lst.parser.reader.iter_log_lines` keeps memory flat regardless
    of file size. The per-line :class:`MinedLine` list preserves input
    order so the downstream Aggregator can compute timestamp-ordered
    metrics (peak rate, first/last seen) without re-sorting.

    Args:
        lines: Iterable of raw log lines; syslog prefixes, if present, are
            stripped internally before feeding drain3.
        sim_th: drain3 similarity threshold in ``[0, 1]``. Lower values
            collapse more aggressively.
        depth: Prefix-tree depth. Higher values create finer templates.
        max_clusters: Cap on retained clusters. drain3 evicts the
            least-recently-used cluster once this cap is exceeded.

    Returns:
        A tuple ``(templates, mined_lines)``:

        * ``templates`` -- :class:`LogTemplate` list sorted by
          ``cluster_id`` ascending.
        * ``mined_lines`` -- :class:`MinedLine` list in input (read)
          order, with timestamps, extracted IPs, and extracted users.
    """
    miner = TemplateMiner(
        persistence_handler=None,
        config=_make_config(sim_th, depth, max_clusters),
    )
    accumulators: dict[int, _TemplateAccumulator] = {}
    mined_lines: list[MinedLine] = []

    for raw in lines:
        timestamp = _extract_timestamp(raw) or datetime.now(UTC)
        stripped = _strip_structured_prefix(raw)
        payload = stripped if stripped else raw
        result = miner.add_log_message(payload)
        cluster_id = int(result["cluster_id"])
        accumulator = accumulators.get(cluster_id)
        if accumulator is None:
            accumulator = _TemplateAccumulator(cluster_id=cluster_id)
            accumulators[cluster_id] = accumulator
        accumulator.update(raw, timestamp)
        mined_lines.append(
            MinedLine(
                cluster_id=cluster_id,
                timestamp=timestamp,
                extracted_ips=extract_ips(raw),
                extracted_users=extract_users(raw),
            )
        )

    templates: list[LogTemplate] = []
    for cluster in sorted(miner.drain.clusters, key=lambda c: c.cluster_id):
        accumulator = accumulators.get(cluster.cluster_id)
        if accumulator is None:
            continue
        fallback = datetime.now(UTC)
        templates.append(
            LogTemplate(
                cluster_id=cluster.cluster_id,
                template=cluster.get_template(),
                size=max(cluster.size, accumulator.size),
                sample_lines=accumulator.samples(),
                first_seen=accumulator.first_seen or fallback,
                last_seen=accumulator.last_seen or fallback,
            )
        )
    return templates, mined_lines

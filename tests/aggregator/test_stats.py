"""Unit tests for ``lst.aggregator.stats``.

Exercises the end-to-end pipeline (reader -> miner -> aggregator) on
the static fixture plus synthetic edge-case inputs for the rate math.
"""

from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from pathlib import Path

import pytest

from lst.aggregator import aggregate
from lst.parser import MinedLine, iter_log_lines, mine_templates
from lst.schemas import AggregatedTemplate, LogTemplate

FIXTURE = Path(__file__).parent.parent / "fixtures" / "auth_sample.log"


@pytest.fixture
def pipeline_output() -> tuple[list[LogTemplate], list[MinedLine]]:
    """End-to-end output of reader + miner on the fixture."""
    return mine_templates(iter_log_lines(FIXTURE))


@pytest.fixture
def aggregated(
    pipeline_output: tuple[list[LogTemplate], list[MinedLine]],
) -> list[AggregatedTemplate]:
    """Aggregator output for the fixture."""
    templates, mined_lines = pipeline_output
    return aggregate(templates, mined_lines)


# Happy-path end-to-end -------------------------------------------------------


def test_aggregate_returns_one_entry_per_template(
    pipeline_output: tuple[list[LogTemplate], list[MinedLine]],
    aggregated: list[AggregatedTemplate],
) -> None:
    """The Aggregator emits exactly one output per input template."""
    templates, _ = pipeline_output
    assert len(aggregated) == len(templates)
    assert all(isinstance(a, AggregatedTemplate) for a in aggregated)


def test_aggregate_preserves_input_template_order(
    pipeline_output: tuple[list[LogTemplate], list[MinedLine]],
    aggregated: list[AggregatedTemplate],
) -> None:
    """Output order matches input template order positionally."""
    templates, _ = pipeline_output
    assert [a.template.cluster_id for a in aggregated] == [t.cluster_id for t in templates]


def test_aggregate_total_count_matches_cluster_line_count(
    pipeline_output: tuple[list[LogTemplate], list[MinedLine]],
    aggregated: list[AggregatedTemplate],
) -> None:
    """``total_count`` equals the number of MinedLines with that cluster_id."""
    _, mined_lines = pipeline_output
    for entry in aggregated:
        expected = sum(1 for ml in mined_lines if ml.cluster_id == entry.template.cluster_id)
        assert entry.total_count == expected


def test_aggregate_total_count_is_at_least_template_size(
    aggregated: list[AggregatedTemplate],
) -> None:
    """Schema invariant: ``total_count >= template.size`` for every entry."""
    for entry in aggregated:
        assert entry.total_count >= entry.template.size


def test_aggregate_peak_rate_never_below_mean_rate(
    aggregated: list[AggregatedTemplate],
) -> None:
    """Schema invariant: ``peak_rate_per_minute >= rate_per_minute`` always."""
    for entry in aggregated:
        assert entry.peak_rate_per_minute >= entry.rate_per_minute


def test_aggregate_sample_ips_capped_and_valid(
    aggregated: list[AggregatedTemplate],
) -> None:
    """``sample_ips`` is capped at five and each entry is a valid IP literal."""
    for entry in aggregated:
        assert len(entry.sample_ips) <= 5
        for literal in entry.sample_ips:
            ip_address(literal)  # raises if invalid


def test_aggregate_sample_users_capped(
    aggregated: list[AggregatedTemplate],
) -> None:
    """``sample_users`` is capped at five."""
    for entry in aggregated:
        assert len(entry.sample_users) <= 5


def test_aggregate_brute_force_has_many_unique_ips(
    aggregated: list[AggregatedTemplate],
) -> None:
    """The brute-force cluster should expose multiple distinct source IPs."""
    brute = max(aggregated, key=lambda a: a.total_count)
    assert brute.unique_ips >= 5
    assert any("203.0.113." in ip for ip in brute.sample_ips)


# Rate math edge cases --------------------------------------------------------


def _mined_line(
    *,
    cluster_id: int = 1,
    ts: datetime,
    ips: list[str] | None = None,
    users: list[str] | None = None,
) -> MinedLine:
    """Tiny factory so individual tests can stay short."""
    return MinedLine(
        cluster_id=cluster_id,
        timestamp=ts,
        extracted_ips=ips or [],
        extracted_users=users or [],
    )


def _log_template(cluster_id: int = 1, size: int = 1) -> LogTemplate:
    now = datetime(2026, 4, 18, 10, 0, 0, tzinfo=UTC)
    return LogTemplate(
        cluster_id=cluster_id,
        template="dummy template",
        size=size,
        sample_lines=["dummy"],
        first_seen=now,
        last_seen=now + timedelta(seconds=size),
    )


def test_aggregate_single_event_cluster_produces_rate_one() -> None:
    """A 1-event cluster gets ``rate=1.0`` and ``peak=1.0`` (no div-by-zero)."""
    template = _log_template(cluster_id=7, size=1)
    lines = [_mined_line(cluster_id=7, ts=datetime(2026, 4, 18, 10, 0, 0, tzinfo=UTC))]
    result = aggregate([template], lines)
    assert len(result) == 1
    assert result[0].rate_per_minute == pytest.approx(1.0)
    assert result[0].peak_rate_per_minute == pytest.approx(1.0)
    assert result[0].total_count == 1


def test_aggregate_burst_inside_one_minute_peak_matches_total() -> None:
    """20 events inside the same minute yield ``peak = total_count``."""
    template = _log_template(cluster_id=2, size=20)
    base = datetime(2026, 4, 18, 10, 0, 0, tzinfo=UTC)
    lines = [_mined_line(cluster_id=2, ts=base + timedelta(seconds=i * 2)) for i in range(20)]
    result = aggregate([template], lines)
    assert result[0].peak_rate_per_minute == pytest.approx(20.0)
    assert result[0].peak_rate_per_minute >= result[0].rate_per_minute


def test_aggregate_five_minute_steady_stream() -> None:
    """10 events evenly across 5 minutes: rate ≈ 2.0/min, peak bucket ≤ 3."""
    template = _log_template(cluster_id=3, size=10)
    base = datetime(2026, 4, 18, 10, 0, 0, tzinfo=UTC)
    lines = [_mined_line(cluster_id=3, ts=base + timedelta(seconds=i * 30)) for i in range(10)]
    result = aggregate([template], lines)
    assert result[0].rate_per_minute == pytest.approx(10 / 4.5, rel=0.05)
    assert result[0].peak_rate_per_minute >= result[0].rate_per_minute


def test_aggregate_dedupes_ips_in_first_seen_order() -> None:
    """Duplicated IPs across lines collapse to a stable first-seen order."""
    template = _log_template(cluster_id=4, size=3)
    base = datetime(2026, 4, 18, 10, 0, 0, tzinfo=UTC)
    lines = [
        _mined_line(cluster_id=4, ts=base, ips=["10.0.0.1"]),
        _mined_line(cluster_id=4, ts=base + timedelta(seconds=30), ips=["10.0.0.2"]),
        _mined_line(cluster_id=4, ts=base + timedelta(seconds=60), ips=["10.0.0.1"]),
    ]
    result = aggregate([template], lines)
    assert result[0].unique_ips == 2
    assert result[0].sample_ips == ["10.0.0.1", "10.0.0.2"]


def test_aggregate_raises_when_template_has_no_lines() -> None:
    """A template without matching :class:`MinedLine` is an upstream bug."""
    template = _log_template(cluster_id=99, size=1)
    with pytest.raises(ValueError, match="cluster_id=99"):
        aggregate([template], [])

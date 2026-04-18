"""Unit tests for ``lst.parser.template_miner``.

Covers the drain3 wrapper, timestamp extraction (ISO / syslog / None),
structured-prefix stripping, sample bookkeeping, the ``max_clusters``
cap, and the per-line :class:`MinedLine` DTO produced alongside the
templates. Uses a small hand-authored fixture under ``tests/fixtures/``
so clustering expectations are reproducible.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lst.parser import MinedLine
from lst.parser.template_miner import (
    _extract_timestamp,
    _strip_structured_prefix,
    mine_templates,
)
from lst.schemas import LogTemplate

FIXTURE = Path(__file__).parent.parent / "fixtures" / "auth_sample.log"


@pytest.fixture
def sample_lines() -> list[str]:
    """Return every non-empty line from the static auth.log fixture."""
    return [line for line in FIXTURE.read_text().splitlines() if line]


# _extract_timestamp ----------------------------------------------------------


def test_extract_timestamp_iso_with_z_suffix() -> None:
    """``Z`` suffix is treated as UTC."""
    result = _extract_timestamp("2026-04-18T10:00:00Z rest of line")
    assert result == datetime(2026, 4, 18, 10, 0, 0, tzinfo=UTC)


def test_extract_timestamp_iso_with_offset() -> None:
    """An explicit offset is preserved instead of being coerced to UTC."""
    result = _extract_timestamp("2026-04-18T10:00:00+02:00 rest of line")
    assert result is not None
    offset = result.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 7200


def test_extract_timestamp_iso_naive_is_promoted_to_utc() -> None:
    """Naive ISO values get UTC attached rather than being left ambiguous."""
    result = _extract_timestamp("2026-04-18T10:00:00 rest of line")
    assert result == datetime(2026, 4, 18, 10, 0, 0, tzinfo=UTC)


def test_extract_timestamp_iso_malformed_returns_none() -> None:
    """Regex-match + ``fromisoformat`` failure falls through to ``None``."""
    assert _extract_timestamp("2026-04-18T10:00:00+25:00 payload") is None


def test_extract_timestamp_syslog_uses_current_year() -> None:
    """Syslog carries no year -- we stamp the current UTC year."""
    result = _extract_timestamp("Apr 18 10:00:00 server sshd[1]: payload")
    assert result is not None
    assert result.year == datetime.now(UTC).year
    assert (result.month, result.day) == (4, 18)
    assert (result.hour, result.minute, result.second) == (10, 0, 0)
    assert result.tzinfo is UTC


def test_extract_timestamp_syslog_invalid_date_returns_none() -> None:
    """Impossible calendar dates (e.g. Feb 30) yield ``None``."""
    assert _extract_timestamp("Feb 30 10:00:00 host proc: payload") is None


def test_extract_timestamp_none_for_unknown_shape() -> None:
    """Lines with no recognisable timestamp yield ``None``."""
    assert _extract_timestamp("no timestamp whatsoever on this line") is None


# _strip_structured_prefix ----------------------------------------------------


def test_strip_structured_prefix_removes_syslog_header() -> None:
    """Syslog ``Mon DD HH:MM:SS host proc[PID]:`` is removed."""
    line = "Apr 18 10:00:00 server sshd[1001]: Failed password for root"
    assert _strip_structured_prefix(line) == "Failed password for root"


def test_strip_structured_prefix_handles_missing_pid() -> None:
    """The ``[PID]`` segment is optional; ``proc:`` alone still strips."""
    line = "Apr 18 10:00:00 server CRON: job ran"
    assert _strip_structured_prefix(line) == "job ran"


def test_strip_structured_prefix_leaves_non_syslog_intact() -> None:
    """ISO-prefixed or structured-JSON lines pass through unchanged."""
    line = '2026-04-18T10:00:00Z json={"k":"v"}'
    assert _strip_structured_prefix(line) == line


# mine_templates --------------------------------------------------------------


def test_mine_templates_fixture_is_findable() -> None:
    """Sanity check: the fixture path resolves to a real file."""
    assert FIXTURE.is_file()


def test_mine_templates_returns_tuple_of_lists(sample_lines: list[str]) -> None:
    """Output is a 2-tuple of ``(templates, mined_lines)`` with correct types."""
    result = mine_templates(sample_lines)
    assert isinstance(result, tuple)
    assert len(result) == 2
    templates, mined_lines = result
    assert isinstance(templates, list)
    assert isinstance(mined_lines, list)
    assert all(isinstance(t, LogTemplate) for t in templates)
    assert all(isinstance(m, MinedLine) for m in mined_lines)


def test_mine_templates_mined_lines_match_input_count(
    sample_lines: list[str],
) -> None:
    """Every input line contributes exactly one :class:`MinedLine`."""
    _, mined_lines = mine_templates(sample_lines)
    assert len(mined_lines) == len(sample_lines)


def test_mine_templates_preserves_input_order(sample_lines: list[str]) -> None:
    """``mined_lines`` follows input order (monotonic timestamps in fixture)."""
    _, mined_lines = mine_templates(sample_lines)
    timestamps = [ml.timestamp for ml in mined_lines]
    assert timestamps == sorted(timestamps)


def test_mine_templates_extracts_ips_on_brute_force_lines(
    sample_lines: list[str],
) -> None:
    """Brute-force lines carry their 203.0.113.X source IPs on the MinedLine."""
    _, mined_lines = mine_templates(sample_lines)
    all_ips = {ip for ml in mined_lines for ip in ml.extracted_ips}
    assert "203.0.113.10" in all_ips
    assert "203.0.113.29" in all_ips


def test_mine_templates_extracts_users_across_patterns(
    sample_lines: list[str],
) -> None:
    """``for``, ``for user``, and ``user`` phrasings all yield usernames."""
    _, mined_lines = mine_templates(sample_lines)
    all_users = {u for ml in mined_lines for u in ml.extracted_users}
    assert "root" in all_users
    assert "admin" in all_users
    assert "testuser" in all_users


def test_mine_templates_identifies_brute_force_cluster(
    sample_lines: list[str],
) -> None:
    """The dominant cluster matches the 20 'Failed password' lines."""
    templates, _ = mine_templates(sample_lines)
    largest = max(templates, key=lambda t: t.size)
    assert largest.size >= 20
    assert "Failed password" in largest.template


def test_mine_templates_caps_sample_lines_at_three(
    sample_lines: list[str],
) -> None:
    """No ``LogTemplate`` ships more than three sample lines."""
    templates, _ = mine_templates(sample_lines)
    for template in templates:
        assert 1 <= len(template.sample_lines) <= 3


def test_mine_templates_emits_aware_ordered_timestamps(
    sample_lines: list[str],
) -> None:
    """Timestamps are timezone-aware and ``last_seen >= first_seen``."""
    templates, _ = mine_templates(sample_lines)
    for template in templates:
        assert template.first_seen.tzinfo is not None
        assert template.last_seen.tzinfo is not None
        assert template.first_seen <= template.last_seen


def test_mine_templates_consumes_lazy_iterable() -> None:
    """The function accepts an arbitrary ``Iterable``, not just a list."""

    def gen() -> Iterator[str]:
        yield "Apr 18 10:00:00 host proc[1]: hello world"
        yield "Apr 18 10:00:01 host proc[2]: hello world again"
        yield "Apr 18 10:00:02 host proc[3]: hello world once more"

    templates, mined_lines = mine_templates(gen())
    assert templates
    assert len(mined_lines) == 3
    assert all(t.size >= 1 for t in templates)


def test_mine_templates_respects_max_clusters_cap() -> None:
    """``max_clusters`` caps the number of retained clusters."""
    diverse = [
        f"Apr 18 10:00:{second:02d} host proc[{second}]: totally distinct event {second}"
        for second in range(20)
    ]
    templates, _ = mine_templates(diverse, max_clusters=2)
    assert len(templates) <= 2


def test_mine_templates_clusters_separate_distinct_shapes(
    sample_lines: list[str],
) -> None:
    """Brute-force, accepted, opened, and closed lines end up in separate clusters."""
    templates, _ = mine_templates(sample_lines)
    bodies = [t.template for t in templates]

    assert any("Failed password" in t for t in bodies)
    assert any("Accepted password" in t for t in bodies)
    assert any("session opened" in t for t in bodies)
    assert any("session closed" in t for t in bodies)

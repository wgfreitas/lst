"""Integration tests for :func:`lst.detector.engine.detect` on IPv6 logs.

Lives in its own file (rather than ``test_engine.py``) so the main-fixture
tests and their hard-coded expectations stay byte-for-byte untouched.

Fixture calibration -- verified empirically by running the deterministic
pipeline (Parser -> Aggregator -> Detector) on the fixture before these
expectations were written:

* 12 ``Failed password`` lines with 12 distinct IPv6 sources spread over
  ~23 minutes -> BruteForce fires: unique_ips=12 >= 10, ratio 1.00 >= 0.8,
  failure verb present; score = min(1.0, 12/20) = 0.60. One line every
  ~2 minutes keeps the per-minute peak at 1.0, so SpikeRule stays silent
  (its absolute arm needs 5/min; its relative arm needs peak >= 3).
* 1 ``[preauth]`` singleton -> Novelty fires at the base score 0.60 (the
  template carries no high-risk keyword).
* 7 ``Accepted publickey`` lines -> benign by construction: the success
  verb suppresses Variety, 7 unique IPs < 10 keeps BruteForce silent,
  total 7 != 1 keeps Novelty silent, and the ~4-minute spacing keeps the
  peak at 1.0 for Spike.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lst.aggregator import aggregate
from lst.detector import detect
from lst.parser import iter_log_lines, mine_templates
from lst.schemas import FlagCategory, FlaggedEvent

FIXTURE = Path(__file__).parent.parent / "fixtures" / "auth_ipv6_sample.log"


@pytest.fixture(scope="module")
def ipv6_flags() -> list[FlaggedEvent]:
    """Run the full deterministic pipeline on the IPv6 fixture once."""
    templates, mined_lines = mine_templates(iter_log_lines(FIXTURE))
    aggregated = aggregate(templates, mined_lines)
    return detect(aggregated)


def test_detect_on_ipv6_fixture_produces_exactly_two_flags(
    ipv6_flags: list[FlaggedEvent],
) -> None:
    """The IPv6 fixture yields exactly one brute-force and one novelty flag."""
    assert len(ipv6_flags) == 2
    categories = [flag.category for flag in ipv6_flags]
    assert categories.count(FlagCategory.BRUTE_FORCE) == 1
    assert categories.count(FlagCategory.NOVELTY) == 1


def test_brute_force_flag_carries_ipv6_evidence(
    ipv6_flags: list[FlaggedEvent],
) -> None:
    """The brute-force flag scores 12/20 and cites IPv6 sources as evidence."""
    brute = next(f for f in ipv6_flags if f.category is FlagCategory.BRUTE_FORCE)
    assert brute.score == pytest.approx(0.60)
    assert brute.aggregated.unique_ips == 12
    assert "2001:db8:bad::1" in brute.aggregated.sample_ips


def test_novelty_flag_scores_base_value(
    ipv6_flags: list[FlaggedEvent],
) -> None:
    """The preauth singleton flags as novelty at the base (non-boosted) score."""
    novelty = next(f for f in ipv6_flags if f.category is FlagCategory.NOVELTY)
    assert novelty.score == pytest.approx(0.60)
    assert novelty.aggregated.total_count == 1

"""Deterministic rule registry.

Each rule is defined in its own file to keep the logic auditable per SRP
(an analyst should be able to read one file and understand one rule).
:data:`ACTIVE_RULES` is the canonical execution order that the engine
consumes -- the order does not affect semantics (the engine's dedup
uses ``(score, priority)``), but listing them here gives a single
place to toggle a rule off during triage.
"""

from __future__ import annotations

from lst.detector.rules.base import Rule
from lst.detector.rules.brute_force import BruteForceRule
from lst.detector.rules.high_risk import HighRiskPatternRule
from lst.detector.rules.novelty import NoveltyRule
from lst.detector.rules.spike import SpikeRule
from lst.detector.rules.variety import VarietyRule

ACTIVE_RULES: list[Rule] = [
    NoveltyRule(),
    BruteForceRule(),
    SpikeRule(),
    HighRiskPatternRule(),
    VarietyRule(),
]
"""Rules the engine runs, in declared order. Semantics are order-agnostic."""

__all__ = [
    "ACTIVE_RULES",
    "BruteForceRule",
    "HighRiskPatternRule",
    "NoveltyRule",
    "Rule",
    "SpikeRule",
    "VarietyRule",
]

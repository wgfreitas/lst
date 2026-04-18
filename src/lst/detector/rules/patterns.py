"""Shared regular expressions for the deterministic rule set.

Kept in a leaf module (no imports from :mod:`lst.detector`) so rules can
consume these patterns without risking an import cycle. All patterns are
pre-compiled at import time -- rule ``evaluate`` methods must never call
:func:`re.compile`.

Three categories live here:

* :data:`FAIL_VERBS_RE` -- matches tokens common to failed-auth phrasings
  (``Failed``, ``invalid``, ``denied``, ``reject``). Used by the BruteForce
  rule to confirm the template is about failures, not a benign but
  IP-diverse signal (e.g. a rotating-proxy health check).
* :data:`SUCCESS_VERBS_RE` -- matches tokens common to accepted-auth
  phrasings (``Accepted``, ``success``, ``authenticated``). Used by the
  Variety rule to suppress firings on normal SSH/auth traffic that
  naturally spans many IPs.
* :data:`HIGH_RISK_PATTERNS` -- named alternation of well-known IOC
  substrings. Ordering is not significant; the matcher is "any-of".
  Each entry is a ``(name, compiled_pattern)`` pair so the Detector can
  cite a stable name in ``context_notes`` regardless of regex shape
  drift.
"""

from __future__ import annotations

import re

FAIL_VERBS_RE: re.Pattern[str] = re.compile(
    r"\b(?:fail(?:ed)?|invalid|denied|reject(?:ed)?)\b",
    re.IGNORECASE,
)
"""Tokens that indicate an authentication or authorisation failure."""

SUCCESS_VERBS_RE: re.Pattern[str] = re.compile(
    r"\b(?:accept(?:ed)?|success(?:ful)?|authenticated)\b",
    re.IGNORECASE,
)
"""Tokens that indicate a successful authentication event."""

HIGH_RISK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("break_in_attempt", re.compile(r"POSSIBLE\s+BREAK-IN\s+ATTEMPT", re.IGNORECASE)),
    ("possible_attack", re.compile(r"possible\s+attack", re.IGNORECASE)),
    ("kernel_panic", re.compile(r"\bkernel\s+panic\b", re.IGNORECASE)),
    (
        "sudo_denied",
        re.compile(
            r"sudo:.*(?:NOT\s+in\s+sudoers|command\s+not\s+allowed)",
            re.IGNORECASE,
        ),
    ),
    ("auth_failure", re.compile(r"\bauthentication\s+failure\b", re.IGNORECASE)),
    ("root_login", re.compile(r"\broot\s+login\b", re.IGNORECASE)),
    ("unauthorized", re.compile(r"\bunauthorized\b|\bunauthorised\b", re.IGNORECASE)),
    ("malware_keyword", re.compile(r"\b(?:malware|trojan|rootkit|backdoor)\b", re.IGNORECASE)),
]
"""Named indicators of compromise / high-risk events.

Each pair is ``(name, compiled_pattern)``. The name is the canonical
tag the Detector writes into ``FlaggedEvent.context_notes`` when the
pattern matches, decoupling the report text from the pattern shape.
"""

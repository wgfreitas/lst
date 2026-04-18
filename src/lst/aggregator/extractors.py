"""Stateless extractors for IPs and usernames in raw log lines.

Both functions are pure (no logging, no I/O, no shared mutable state)
so unit tests are trivial and the Detector stage can reuse them for
contextual checks without worrying about state leaks.

Scope notes for future maintainers:

* ``extract_ips`` is IPv4-only in the MVP. Adding IPv6 is a one-line
  regex extension -- :func:`ipaddress.ip_address` already accepts both
  families, so only the syntactic pattern needs to change.
* ``extract_users`` uses a short whitelist of keyword phrasings that
  cover OpenSSH / PAM auth messages. New phrasings (``logged in as``,
  ``authenticated user``, etc.) can be added to the alternation -- the
  ordering matters, keep the longest prefix first.
"""

from __future__ import annotations

import re
from ipaddress import ip_address

_IP_RE = re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")
"""Syntactic IPv4 pattern; numerical validity is checked downstream."""

_USER_RE = re.compile(r"\b(?:for user|by user|for|user)\s+(\w+)")
"""Username capture. Alternation is ORDER-SENSITIVE: longer prefixes
(``for user``, ``by user``) must come before their shorter substrings
so that "opened for user admin" captures ``admin`` rather than the
literal keyword ``user``."""


def extract_ips(line: str) -> list[str]:
    """Return every valid IPv4 literal found in ``line``.

    Candidates are first matched syntactically via ``_IP_RE``, then
    validated via :func:`ipaddress.ip_address`. Syntactically-valid but
    numerically-invalid literals (e.g. ``999.999.999.999``) are dropped
    silently -- logging them would noisily explode on worm-style
    payloads that include malformed IPs on purpose.

    Order of occurrence is preserved and duplicates are retained; the
    caller is responsible for de-duplication if it cares.

    Args:
        line: Raw log line.

    Returns:
        IPv4 literals in order of occurrence, possibly with duplicates.

    Example:
        >>> extract_ips("Failed from 1.2.3.4 and 999.999.999.999 and 1.2.3.4")
        ['1.2.3.4', '1.2.3.4']
    """
    found: list[str] = []
    for candidate in _IP_RE.findall(line):
        try:
            ip_address(candidate)
        except ValueError:
            continue
        found.append(candidate)
    return found


def extract_users(line: str) -> list[str]:
    """Return every username captured by auth-style phrasings in ``line``.

    Heuristics recognised (in priority order):

    * ``for user <name>`` (PAM session lines)
    * ``by user <name>`` (PAM session lines)
    * ``for <name>`` (OpenSSH password attempts)
    * ``user <name>`` (``invalid user <name>`` and similar)

    Order of occurrence is preserved and duplicates are retained; the
    caller is responsible for de-duplication if it cares.

    Args:
        line: Raw log line.

    Returns:
        Usernames in order of occurrence.

    Example:
        >>> extract_users("Failed password for root from 1.2.3.4")
        ['root']
    """
    return _USER_RE.findall(line)

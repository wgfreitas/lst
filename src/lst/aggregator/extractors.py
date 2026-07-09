"""Stateless extractors for IPs and usernames in raw log lines.

Both functions are pure (no logging, no I/O, no shared mutable state)
so unit tests are trivial and the Detector stage can reuse them for
contextual checks without worrying about state leaks.

Scope notes for future maintainers:

* ``extract_ips`` handles both IPv4 and IPv6. The regex stays
  deliberately liberal -- it only shapes candidates; the validation
  step downstream is the numeric gatekeeper. Two IPv6 decisions worth
  knowing: zone-ID'd literals (``fe80::1%eth0``) are captured whole
  and then discarded -- never silently stripped down to ``fe80::1`` --
  and IPv4-mapped literals (``::ffff:192.0.2.1``) are returned
  verbatim as a single IPv6 token, without normalisation and without
  also reporting the embedded IPv4.
* ``extract_users`` uses a short whitelist of keyword phrasings that
  cover OpenSSH / PAM auth messages. New phrasings (``logged in as``,
  ``authenticated user``, etc.) can be added to the alternation -- the
  ordering matters, keep the longest prefix first.
"""

from __future__ import annotations

import re
from ipaddress import ip_address

_IP_RE = re.compile(
    # IPv6 arm. It must come FIRST: re.findall resumes scanning after each
    # match, so matching "::ffff:192.0.2.1" whole here means the IPv4 arm
    # never sees the embedded dotted quad. Every group is non-capturing so
    # findall returns whole matches rather than group tuples.
    r"(?<![\w:])"  # not glued to a word char or ':' (kills std::string)
    r"(?=[0-9A-Fa-f:]*[0-9A-Fa-f])"  # >=1 hex digit ahead: a bare " :: "
    # separator never becomes a candidate (ip_address accepts '::' as the
    # unspecified address, so the regex must reject it, not the validator)
    r"(?:[0-9A-Fa-f]{0,4}:){2,7}"  # liberal colon-groups: full, compressed,
    # and even invalid shapes (timestamps, MACs) all pass; validation decides
    r"(?:\d{1,3}(?:\.\d{1,3}){3}|[0-9A-Fa-f]{1,4})?"  # tail: embedded IPv4
    # (mapped form, tried first so it wins over a bare hex prefix) or the
    # final hex group
    r"(?:%[\w.]+)?"  # zone ID is consumed so the WHOLE zoned token reaches
    # validation and is discarded there -- never silently stripped
    r"(?![\w:%])"  # not glued on the right; '%' stops backtracking from
    # shedding a half-matched zone and returning the bare address
    # IPv4 arm -- byte-for-byte the original pattern, so IPv4 extraction
    # cannot regress.
    r"|\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"
)
"""Syntactic IPv4/IPv6 pattern; numerical validity is checked downstream."""

_USER_RE = re.compile(r"\b(?:for user|by user|for|user)\s+(\w+)")
"""Username capture. Alternation is ORDER-SENSITIVE: longer prefixes
(``for user``, ``by user``) must come before their shorter substrings
so that "opened for user admin" captures ``admin`` rather than the
literal keyword ``user``."""


def extract_ips(line: str) -> list[str]:
    """Return every valid IP literal (IPv4 or IPv6) found in ``line``.

    Candidates are first matched syntactically via ``_IP_RE``, then
    validated via :func:`ipaddress.ip_address`. Syntactically-valid but
    numerically-invalid literals (e.g. ``999.999.999.999``, or a
    ``10:00:01`` timestamp that happens to look like colon-groups) are
    dropped silently -- logging them would noisily explode on
    worm-style payloads that include malformed IPs on purpose.

    Zone-ID'd IPv6 literals (``fe80::1%eth0``) are captured whole and
    then discarded here: :func:`ipaddress.ip_address` accepts scoped
    addresses on Python 3.9+, so the rejection is an explicit check
    rather than a validation failure. Discarding beats stripping the
    zone -- a link-local address is only meaningful relative to the
    host that logged it, and a silent strip would report an address
    the line never contained.

    IPv4-mapped literals (``::ffff:192.0.2.1``) are returned verbatim
    as one IPv6 token: no normalisation, and the embedded IPv4 is not
    reported separately.

    Order of occurrence is preserved and duplicates are retained; the
    caller is responsible for de-duplication if it cares.

    Args:
        line: Raw log line.

    Returns:
        IP literals in order of occurrence, possibly with duplicates.

    Example:
        >>> extract_ips("Failed from 2001:db8::1 and 999.999.999.999 and 1.2.3.4")
        ['2001:db8::1', '1.2.3.4']
    """
    found: list[str] = []
    for candidate in _IP_RE.findall(line):
        if "%" in candidate:
            # Scoped (zone-ID'd) IPv6: deliberately discarded, see docstring.
            continue
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

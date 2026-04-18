"""Unit tests for ``lst.aggregator.extractors``.

Extractors are pure functions, so tests need only character-level
inputs -- no fixtures, no I/O.
"""

from lst.aggregator.extractors import extract_ips, extract_users

# extract_ips -----------------------------------------------------------------


def test_extract_ips_finds_all_valid_ipv4() -> None:
    """Multiple syntactically valid IPv4 addresses are all returned."""
    line = "Failed from 203.0.113.10 relayed by 198.51.100.42 to 192.0.2.1"
    assert extract_ips(line) == ["203.0.113.10", "198.51.100.42", "192.0.2.1"]


def test_extract_ips_drops_numerically_invalid_octets() -> None:
    """Syntactically-valid but numerically-invalid IPs are filtered out."""
    line = "Mixed: 1.2.3.4 and 999.999.999.999 and 256.0.0.1 and 10.0.0.1"
    assert extract_ips(line) == ["1.2.3.4", "10.0.0.1"]


def test_extract_ips_returns_empty_for_no_ip() -> None:
    """Lines with no IPv4 shape yield an empty list (not ``None``)."""
    assert extract_ips("session opened for user admin by (uid=0)") == []


def test_extract_ips_preserves_order_and_duplicates() -> None:
    """Duplicates are retained in first-seen order; dedup is the caller's job."""
    line = "From 1.1.1.1 via 2.2.2.2 via 1.1.1.1 again"
    assert extract_ips(line) == ["1.1.1.1", "2.2.2.2", "1.1.1.1"]


def test_extract_ips_ignores_dotted_decimals_inside_versions() -> None:
    """Version-looking tokens (``1.2.3`` with only 3 octets) do not match."""
    assert extract_ips("running version 1.2.3 on arch") == []


# extract_users ---------------------------------------------------------------


def test_extract_users_after_for() -> None:
    """OpenSSH ``for <user>`` phrasing captures the user token."""
    assert extract_users("Failed password for root from 1.2.3.4 port 22") == ["root"]


def test_extract_users_after_user_keyword() -> None:
    """``invalid user <name>`` captures the name."""
    assert extract_users("Connection closed by invalid user testuser 1.2.3.4") == ["testuser"]


def test_extract_users_after_by_user() -> None:
    """``by user <name>`` (PAM session close) captures the name."""
    assert extract_users("session closed by user admin") == ["admin"]


def test_extract_users_after_for_user_prefers_longer_prefix() -> None:
    """``for user <name>`` must capture ``<name>``, not the literal word ``user``."""
    line = "pam_unix(sshd:session): session opened for user admin by (uid=0)"
    assert extract_users(line) == ["admin"]


def test_extract_users_returns_empty_for_no_match() -> None:
    """Lines with no keyword phrasing return an empty list."""
    assert extract_users("ntpd: adjusting clock frequency by 0.002 ppm") == []


def test_extract_users_collects_multiple_occurrences() -> None:
    """Two independent matches on one line are both captured, in order."""
    line = "Failed password for root; later session opened for user admin"
    assert extract_users(line) == ["root", "admin"]

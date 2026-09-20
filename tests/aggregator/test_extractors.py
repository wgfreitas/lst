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


# extract_ips: IPv6 -----------------------------------------------------------


def test_extract_ips_finds_compressed_ipv6() -> None:
    """The ``::``-compressed form is extracted."""
    assert extract_ips("connect from 2001:db8::1 port 22") == ["2001:db8::1"]


def test_extract_ips_finds_full_form_ipv6() -> None:
    """The full eight-group form is extracted verbatim."""
    line = "addr 2001:0db8:85a3:0000:0000:8a2e:0370:7334 announced"
    assert extract_ips(line) == ["2001:0db8:85a3:0000:0000:8a2e:0370:7334"]


def test_extract_ips_finds_ipv6_loopback() -> None:
    """The loopback ``::1`` is extracted."""
    assert extract_ips("connection from ::1 port 22") == ["::1"]


def test_extract_ips_finds_link_local_without_zone() -> None:
    """A link-local address WITHOUT a zone ID is valid and extracted."""
    assert extract_ips("neighbor fe80::1 is reachable") == ["fe80::1"]


def test_extract_ips_returns_ipv4_mapped_as_single_ipv6_token() -> None:
    """IPv4-mapped comes back as ONE verbatim IPv6 item.

    The embedded dotted quad must not surface as a second, separate
    IPv4 item, and the token is not normalised (``::ffff:c000:201``).
    """
    result = extract_ips("proxy via ::ffff:192.0.2.1 established")
    assert result == ["::ffff:192.0.2.1"]
    assert "192.0.2.1" not in result


def test_extract_ips_mixed_families_in_order_of_occurrence() -> None:
    """IPv6 and IPv4 on one line are both returned, in line order."""
    line = "from 2001:db8::1 and 203.0.113.5"
    assert extract_ips(line) == ["2001:db8::1", "203.0.113.5"]


def test_extract_ips_on_real_ssh_failure_line_with_ipv6() -> None:
    """A realistic sshd failure line yields exactly the IPv6 source."""
    line = "Failed password for root from 2001:db8:dead:beef::10 port 22 ssh2"
    assert extract_ips(line) == ["2001:db8:dead:beef::10"]


def test_extract_ips_rejects_syslog_timestamp() -> None:
    """``10:00:01`` may match syntactically but fails IP validation."""
    line = "Apr 18 10:00:01 server sshd[1001]: session opened for user admin"
    assert extract_ips(line) == []


def test_extract_ips_discards_zoned_ipv6_entirely() -> None:
    """A zone-ID'd literal is dropped whole -- never stripped to ``fe80::1``.

    Capturing ``fe80::1`` here would silently fabricate a zone-less
    address the line never carried; the decision is to discard.
    """
    assert extract_ips("input from fe80::1%eth0 port 22") == []


def test_extract_ips_rejects_mac_address() -> None:
    """Six colon-groups without ``::`` are not a valid IPv6 address."""
    assert extract_ips("link aa:bb:cc:dd:ee:ff detected") == []


def test_extract_ips_ignores_cpp_scope_operator() -> None:
    """``std::string`` in a leaked stack trace produces no candidate."""
    assert extract_ips("error in std::string constructor") == []


def test_extract_ips_still_drops_invalid_ipv4_octets() -> None:
    """The pre-IPv6 behaviour for bad IPv4 literals is unchanged."""
    assert extract_ips("probe from 999.999.999.999 dropped") == []


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


# extract_users: PAM key=value ``user=<name>`` -------------------------------


def test_extract_users_after_user_equals_on_pam_auth_failure_line() -> None:
    """The PAM ``user=<name>`` key=value token captures ``<name>``."""
    line = (
        "pam_unix(sshd:auth): authentication failure; logname= uid=0 euid=0 "
        "tty=ssh ruser= rhost=203.0.113.5 user=root"
    )
    assert extract_users(line) == ["root"]


def test_extract_users_after_for_is_unchanged_by_kv_heuristic() -> None:
    """Regression: the OpenSSH ``for <name>`` phrasing still captures exactly the name."""
    assert extract_users("Failed password for admin from 203.0.113.9 port 22 ssh2") == ["admin"]


def test_extract_users_ignores_empty_ruser_key() -> None:
    """An empty ``ruser=`` on the same line is not a match and does not shadow ``user=``."""
    assert extract_users("ruser= rhost=203.0.113.5 user=bob") == ["bob"]


def test_extract_users_ignores_populated_ruser_key() -> None:
    """``ruser=<remote>`` is the remote user, not the target account: never captured."""
    assert extract_users("ruser=eve rhost=203.0.113.5 user=bob") == ["bob"]


def test_extract_users_never_captures_other_kv_keys() -> None:
    """``logname=``, ``uid=`` and ``euid=`` are not usernames even when ``user=`` is absent."""
    line = "authentication failure; logname=root uid=0 euid=0 tty=ssh ruser= rhost=203.0.113.5"
    assert extract_users(line) == []


def test_extract_users_mixed_forms_keep_order_and_duplicates() -> None:
    """``for <name>`` followed by ``user=<name>`` yields both hits, in line order."""
    line = "Accepted password for alice from 203.0.113.7 port 22 ssh2 user=alice"
    assert extract_users(line) == ["alice", "alice"]


def test_extract_users_for_user_prefix_still_wins_over_kv_arm() -> None:
    """Regression: ``for user <name>`` keeps capturing ``<name>`` with the ``user=`` arm present."""
    assert extract_users("session opened for user admin by (uid=0)") == ["admin"]


def test_extract_users_user_equals_without_value_is_ignored() -> None:
    """A dangling ``user=`` at end of line yields nothing (no exception)."""
    assert extract_users("authentication failure; user=") == []


def test_extract_users_user_double_equals_is_ignored() -> None:
    """``user==root`` is malformed: the value must start right after a single ``=``."""
    assert extract_users("authentication failure; user==root") == []


def test_extract_users_empty_line_returns_empty() -> None:
    """The empty string is well-formed input and yields an empty list."""
    assert extract_users("") == []

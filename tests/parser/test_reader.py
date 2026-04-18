"""Unit tests for ``lst.parser.reader``.

Cover streaming behaviour, whitespace handling, eager path validation,
and decoder error policy. All tests use ``tmp_path`` so no fixture files
are required.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from lst.parser.reader import iter_log_lines


def test_iter_log_lines_yields_each_line(tmp_path: Path) -> None:
    """Happy path: every non-empty line is yielded once, in order."""
    log = tmp_path / "auth.log"
    log.write_text("first\nsecond\nthird\n", encoding="utf-8")

    assert list(iter_log_lines(log)) == ["first", "second", "third"]


def test_iter_log_lines_strips_trailing_whitespace(tmp_path: Path) -> None:
    """Trailing ``\\r``, spaces, and tabs are removed before yielding."""
    log = tmp_path / "auth.log"
    log.write_bytes(b"padded   \r\ntabs\t\t\nclean\n")

    assert list(iter_log_lines(log)) == ["padded", "tabs", "clean"]


def test_iter_log_lines_skips_empty_and_whitespace_only(tmp_path: Path) -> None:
    """Empty lines and whitespace-only lines are dropped from the stream."""
    log = tmp_path / "auth.log"
    log.write_text("real\n\n   \nreal-again\n", encoding="utf-8")

    assert list(iter_log_lines(log)) == ["real", "real-again"]


def test_iter_log_lines_raises_for_missing_file_eagerly(tmp_path: Path) -> None:
    """Missing path fails at call time, before any iteration occurs."""
    missing = tmp_path / "does-not-exist.log"

    with pytest.raises(FileNotFoundError, match="does-not-exist"):
        iter_log_lines(missing)


def test_iter_log_lines_raises_for_directory(tmp_path: Path) -> None:
    """Directories fail the ``is_file()`` gate, same as missing files."""
    with pytest.raises(FileNotFoundError):
        iter_log_lines(tmp_path)


def test_iter_log_lines_replaces_invalid_bytes(tmp_path: Path) -> None:
    """Invalid bytes are substituted per ``errors='replace'`` (U+FFFD)."""
    log = tmp_path / "auth.log"
    log.write_bytes(b"ok\n\xff\xfe broken\nok-again\n")

    lines = list(iter_log_lines(log))

    assert lines[0] == "ok"
    assert "\ufffd" in lines[1]
    assert lines[-1] == "ok-again"


def test_iter_log_lines_returns_iterator_not_list(tmp_path: Path) -> None:
    """Return type is a lazy iterator so huge files do not balloon memory."""
    log = tmp_path / "auth.log"
    log.write_text("a\nb\n", encoding="utf-8")

    result = iter_log_lines(log)

    assert isinstance(result, Iterator)
    assert not isinstance(result, list)


def test_iter_log_lines_accepts_str_path(tmp_path: Path) -> None:
    """``path`` accepts both ``Path`` and ``str`` (standard pathlib idiom)."""
    log = tmp_path / "auth.log"
    log.write_text("only-line\n", encoding="utf-8")

    assert list(iter_log_lines(str(log))) == ["only-line"]

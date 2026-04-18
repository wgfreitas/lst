"""Streaming reader for plain-text log files.

A single public function, ``iter_log_lines``, produces an iterator over
non-empty stripped log lines without materialising the whole file in
memory. The function validates the path eagerly (so a missing file
raises at call time, not on first ``next()``) and then delegates to a
private generator for the actual I/O.
"""

from collections.abc import Iterator
from pathlib import Path


def iter_log_lines(
    path: str | Path,
    *,
    encoding: str = "utf-8",
    errors: str = "replace",
) -> Iterator[str]:
    """Yield non-empty stripped log lines from ``path`` one at a time.

    Trailing whitespace (``\\r``, ``\\n``, spaces, tabs) is stripped and
    purely-whitespace lines are dropped, so callers can treat each yielded
    value as "one real log line". File existence is checked eagerly so a
    missing path raises ``FileNotFoundError`` before any iteration begins.

    Args:
        path: Filesystem path to the log file.
        encoding: Text encoding used to decode the file (default ``utf-8``).
        errors: Codec error policy (default ``replace`` -- invalid bytes
            are substituted with U+FFFD so a corrupt byte does not abort
            the stream).

    Returns:
        An iterator of non-empty stripped log lines.

    Raises:
        FileNotFoundError: if ``path`` does not point at a regular file.
    """
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"log file not found: {resolved}")
    return _stream(resolved, encoding, errors)


def _stream(path: Path, encoding: str, errors: str) -> Iterator[str]:
    """Yield stripped non-empty lines from an already-validated ``path``."""
    with path.open(encoding=encoding, errors=errors) as handle:
        for raw in handle:
            stripped = raw.rstrip()
            if stripped:
                yield stripped

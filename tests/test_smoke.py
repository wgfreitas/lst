"""Smoke tests for the ``lst`` package.

These tests verify that the minimal package scaffold is importable and that
the public version identifier has a semver-compatible shape. They exist to
prove the packaging story works before any feature code is added.
"""

import lst


def test_package_imports() -> None:
    """Importing ``lst`` succeeds and exposes a non-empty version string."""
    assert isinstance(lst.__version__, str)
    assert lst.__version__, "__version__ must be a non-empty string"


def test_version_follows_semver() -> None:
    """Version has at least ``major.minor`` with numeric components."""
    parts = lst.__version__.split(".")
    assert len(parts) >= 2, f"version {lst.__version__!r} lacks a minor component"
    assert parts[0].isdigit(), f"major {parts[0]!r} is not numeric"
    assert parts[1].isdigit(), f"minor {parts[1]!r} is not numeric"

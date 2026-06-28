"""Tests for the Typer CLI in :mod:`lst.cli`.

CliRunner is used for in-process invocation so the tests are fast and
capture stdout/stderr cleanly. The live-LLM path is not exercised here
(it is covered in :mod:`tests.test_pipeline` via direct client
injection); CLI coverage focuses on dry-run, error messages, and the
two-command help surface.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from lst import __version__
from lst.cli import app

_FIXTURE = Path(__file__).parent / "fixtures" / "auth_sample.log"


@pytest.fixture
def runner() -> CliRunner:
    """Return a CliRunner (Click 8.3+ keeps stdout/stderr separate by default)."""
    return CliRunner()


def test_cli_version(runner: CliRunner) -> None:
    """``lst version`` prints the package version."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert f"lst {__version__}" in result.stdout


def test_cli_scan_missing_file(runner: CliRunner) -> None:
    """A non-existent log path yields exit 2 and a pt-BR error."""
    result = runner.invoke(app, ["scan", "/nao/existe.log"])
    assert result.exit_code == 2
    assert "não encontrado" in result.stderr


def test_cli_scan_dry_run_to_stdout(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Dry-run scan streams the Markdown report to stdout (no API key needed)."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # avoid picking up a developer .env
    result = runner.invoke(app, ["scan", str(_FIXTURE), "--dry-run"])
    assert result.exit_code == 0, result.stderr
    assert "# Relatório de Triagem" in result.stdout
    assert "[dry-run]" in result.stdout


def test_cli_scan_dry_run_to_file(
    runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``-o`` writes the Markdown to a file and keeps stdout quiet."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    out_path = tmp_path / "report.md"
    result = runner.invoke(
        app,
        ["scan", str(_FIXTURE), "--dry-run", "-o", str(out_path)],
    )
    assert result.exit_code == 0, result.stderr
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert "# Relatório de Triagem" in content
    assert "[dry-run]" in content


def test_cli_scan_without_api_key(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A missing API key outside of dry-run is a clear, exit-1 failure."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # prevents picking up a developer .env
    result = runner.invoke(app, ["scan", str(_FIXTURE)])
    assert result.exit_code == 1
    assert "LLM_API_KEY" in result.stderr
    assert "não configurada" in result.stderr


def test_cli_help_lists_commands(runner: CliRunner) -> None:
    """Top-level ``--help`` surfaces both registered commands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    normalised = " ".join(result.stdout.split())
    assert "scan" in normalised
    assert "version" in normalised

"""Tests for the Typer CLI in :mod:`lst.cli`.

CliRunner is used for in-process invocation so the tests are fast and
capture stdout/stderr cleanly. The live-LLM path is not exercised here
(it is covered in :mod:`tests.test_pipeline` via direct client
injection); CLI coverage focuses on dry-run, error messages, and the
three-command help surface.

The ``env-check`` tests cover only the file/exit-code layer (case IDs
E1, E2 and the CLI side of N1, L1, E3/E4); the parse/check/render logic
is specified in :mod:`tests.test_envcheck`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from lst import __version__
from lst.cli import app

_FIXTURE = Path(__file__).parent / "fixtures" / "auth_sample.log"
_EXAMPLE_PATH = Path(__file__).resolve().parent.parent / ".env.example"

_FULL_ENV = (
    "LLM_API_KEY=fake-key\n"
    "LLM_MODEL=fake-model\n"
    "LLM_BASE_URL=http://fake\n"
    "LLM_TIMEOUT_SECONDS=fake-timeout\n"
    "LLM_MAX_RETRIES=fake-retries\n"
    "LLM_MAX_TOKENS=fake-tokens\n"
    "LLM_STRUCTURED_MODE=fake-mode\n"
    "LLM_PARSE_RETRIES=fake-parse-retries\n"
)

_SENTINEL = "VALOR-QUE-NAO-PODE-VAZAR"


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


# --- env-check ----------------------------------------------------------------


def test_cli_help_lists_env_check(runner: CliRunner) -> None:
    """Top-level ``--help`` surfaces the additive ``env-check`` command."""
    invocation = runner.invoke(app, ["--help"])
    assert invocation.exit_code == 0
    assert "env-check" in " ".join(invocation.stdout.split())


def _write_contract(directory: Path) -> Path:
    """Copy the real ``.env.example`` into ``directory`` and return its path."""
    contract_path = directory / ".env.example"
    contract_path.write_text(_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return contract_path


def test_n1_env_check_cli_reports_ok_and_exits_0(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Default paths in the current directory: a complete .env prints the OK summary."""
    monkeypatch.chdir(tmp_path)
    _write_contract(tmp_path)
    (tmp_path / ".env").write_text(_FULL_ENV, encoding="utf-8")

    invocation = runner.invoke(app, ["env-check"])

    assert invocation.exit_code == 0, invocation.stderr
    assert invocation.stdout.strip() == "OK: 8 chaves conferidas, sem problemas"


def test_l1_env_check_cli_exits_1_on_error_finding(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``--env`` / ``--example`` select the files; an empty required key is exit 1."""
    monkeypatch.chdir(tmp_path)
    contract_path = _write_contract(tmp_path)
    env_path = tmp_path / "local.env"
    env_path.write_text("LLM_API_KEY=\n", encoding="utf-8")

    invocation = runner.invoke(
        app,
        ["env-check", "--env", str(env_path), "--example", str(contract_path)],
    )

    assert invocation.exit_code == 1
    assert "[ERRO] LLM_API_KEY" in invocation.stdout
    assert "1 erro(s), 0 aviso(s)" in invocation.stdout


def test_e1_env_check_cli_missing_env_file_is_exit_2(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """No ``.env`` in the current directory -> pt-BR error on stderr, exit 2."""
    monkeypatch.chdir(tmp_path)
    _write_contract(tmp_path)

    invocation = runner.invoke(app, ["env-check"])

    assert invocation.exit_code == 2
    assert "Erro: arquivo não encontrado: .env" in invocation.stderr
    assert invocation.stdout == ""


def test_e2_env_check_cli_missing_example_file_is_exit_2(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """No ``.env.example`` in the current directory -> pt-BR error on stderr, exit 2."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(_FULL_ENV, encoding="utf-8")

    invocation = runner.invoke(app, ["env-check"])

    assert invocation.exit_code == 2
    assert "Erro: arquivo não encontrado: .env.example" in invocation.stderr
    assert invocation.stdout == ""


def test_e1_env_check_cli_unreadable_env_file_is_exit_2_without_traceback(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A .env that is not UTF-8 is a pt-BR read error (exit 2), never a traceback."""
    monkeypatch.chdir(tmp_path)
    _write_contract(tmp_path)
    (tmp_path / ".env").write_bytes(b"LLM_API_KEY=\xff\xfe\n")

    invocation = runner.invoke(app, ["env-check"])

    assert invocation.exit_code == 2
    assert "Erro: não foi possível ler o arquivo: .env" in invocation.stderr
    assert not isinstance(invocation.exception, Exception)
    assert "Traceback" not in invocation.stdout + invocation.stderr


def test_e3_e4_env_check_cli_never_prints_values_or_keyless_lines(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Sentinel values, a legacy alias, an unknown key and a keyless line: none is echoed."""
    monkeypatch.chdir(tmp_path)
    _write_contract(tmp_path)
    env_lines = [f"{line.split('=', 1)[0]}={_SENTINEL}" for line in _FULL_ENV.splitlines()]
    env_lines += [f"OLLAMA_API_KEY={_SENTINEL}", f"LST_HTTP_TIMEOUT={_SENTINEL}", _SENTINEL]
    (tmp_path / ".env").write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    invocation = runner.invoke(app, ["env-check"])

    assert invocation.exit_code == 0, invocation.stderr
    assert "[AVISO] linha 11: malformada (ignorada)" in invocation.stdout
    assert "[AVISO] LST_HTTP_TIMEOUT: chave desconhecida (linha 10)" in invocation.stdout
    assert "0 erro(s), 3 aviso(s)" in invocation.stdout
    assert _SENTINEL not in invocation.stdout
    assert _SENTINEL not in invocation.stderr

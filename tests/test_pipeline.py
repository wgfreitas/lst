"""Integration tests for :func:`lst.pipeline.run_pipeline`.

The orchestrator wires all five stages together, so each test exercises
the real Parser, Aggregator, Detector, and Reporter. Only the LLM
Explainer is stubbed -- with :class:`FakeLLMClient` for the happy path
and with the dry-run placeholder for the offline path.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from lst.config import Settings
from lst.pipeline import run_pipeline

_FIXTURE = Path(__file__).parent / "fixtures" / "auth_sample.log"


class FakeLLMClient:
    """Queue-based :class:`~lst.explainer.client.LLMClient` stand-in."""

    def __init__(self, responses: list[str]) -> None:
        self.responses: list[str] = list(responses)
        self.call_count = 0

    async def complete(
        self,
        system: str,
        user: str,
        *,
        model: str,
        timeout: float,
        json_mode: bool = True,
    ) -> tuple[str, int]:
        self.call_count += 1
        if not self.responses:
            raise RuntimeError("FakeLLMClient: no more responses queued")
        return self.responses.pop(0), 42


def _settings() -> Settings:
    """Return a :class:`Settings` that ignores any local ``.env`` file."""
    return Settings(
        _env_file=None,
        llm_api_key="test-api-key",
        llm_model="test-model",
    )


def _brute_force_response() -> str:
    return (
        '{"explanation": "Tentativa de brute force contra SSH via múltiplos IPs.", '
        '"severity": "high", '
        '"next_action": "Bloquear os IPs ofensivos no firewall."}'
    )


def _break_in_response() -> str:
    return (
        '{"explanation": "Tentativa de acesso com mapeamento reverso suspeito.", '
        '"severity": "critical", '
        '"next_action": "Investigar o host malicious.example.com."}'
    )


def _invalid_user_response() -> str:
    return (
        '{"explanation": "Conexão encerrada por usuário inválido.", '
        '"severity": "medium", '
        '"next_action": "Revisar logs do IP 198.51.100.42."}'
    )


async def test_pipeline_end_to_end_on_fixture() -> None:
    """The real pipeline + a fake LLM produces a complete Markdown report."""
    fake = FakeLLMClient(
        [
            _brute_force_response(),
            _break_in_response(),
            _invalid_user_response(),
        ]
    )
    markdown = await run_pipeline(_FIXTURE, _settings(), client=fake)

    assert "Relatório de Triagem" in markdown
    assert "brute_force_by_ip_cardinality" in markdown
    for ip in ("203.0.113.10", "203.0.113.11", "203.0.113.12"):
        assert ip in markdown
    assert "[dry-run]" not in markdown
    assert fake.call_count >= 1


async def test_pipeline_dry_run() -> None:
    """Dry-run skips the LLM, emits placeholders, and never needs an API key."""
    settings = Settings(
        _env_file=None,
        llm_api_key="irrelevant-in-dry-run",
        llm_model="test-model",
    )
    markdown = await run_pipeline(_FIXTURE, settings, dry_run=True)

    assert "[dry-run] explicação não gerada" in markdown
    assert "[dry-run] ação não sugerida" in markdown
    assert "Relatório de Triagem" in markdown


async def test_pipeline_empty_log(tmp_path: Path) -> None:
    """An empty log yields the Reporter's empty-state placeholder."""
    empty = tmp_path / "empty.log"
    empty.write_text("", encoding="utf-8")

    markdown = await run_pipeline(empty, _settings(), dry_run=True)

    assert "Nenhum evento suspeito" in markdown


async def test_pipeline_missing_file(tmp_path: Path) -> None:
    """A missing path propagates ``FileNotFoundError`` to the caller."""
    missing = tmp_path / "does_not_exist.log"
    with pytest.raises(FileNotFoundError):
        await run_pipeline(missing, _settings(), dry_run=True)


async def test_pipeline_logs_each_stage(caplog: pytest.LogCaptureFixture) -> None:
    """Every stage emits an INFO line so ``--verbose`` users see progress."""
    with caplog.at_level(logging.INFO, logger="lst.pipeline"):
        await run_pipeline(_FIXTURE, _settings(), dry_run=True)

    messages = " | ".join(record.getMessage() for record in caplog.records)
    assert "Pipeline started" in messages
    assert "Stage 1" in messages
    assert "Stage 2" in messages
    assert "Stage 3" in messages
    assert "Stage 4" in messages
    assert "Stage 5" in messages
    assert "Pipeline complete" in messages


async def test_pipeline_surfaces_discarded_events_in_report() -> None:
    """Events the LLM can never explain land in the report's discarded footer."""
    # Junk on every call: with parse_retries the engine exhausts retries and
    # discards each flagged event instead of dropping it silently.
    fake = FakeLLMClient(["not valid json"] * 20)
    markdown = await run_pipeline(_FIXTURE, _settings(), client=fake)
    assert "## Eventos não explicados" in markdown
    assert "investigação manual" in markdown
    assert "Nenhum evento suspeito" not in markdown

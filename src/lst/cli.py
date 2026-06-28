"""LST command-line interface built on Typer.

The CLI is deliberately thin: it parses flags, configures logging,
loads :class:`Settings`, and delegates to :func:`lst.pipeline.run_pipeline`.
Everything that is not argument handling or error presentation lives in
the pipeline module so unit tests can exercise it without CliRunner.

Error handling policy: every known failure mode is mapped to a short
pt-BR message and a non-zero exit code. Tracebacks are suppressed on
purpose -- an ETIR analyst running ``lst scan`` wants to know what to
fix, not to read a Python stack. ``--verbose`` turns on ``INFO``
logging, which shows each pipeline stage completing; the raw exception
message is included in every error line so root-cause information is
never lost, just reframed.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import typer
from openai import APITimeoutError, AuthenticationError
from pydantic import ValidationError

from lst import __version__
from lst.config import Settings
from lst.pipeline import run_pipeline

app = typer.Typer(
    name="lst",
    help="Triagem de logs de segurança via pipeline determinístico + LLM.",
    no_args_is_help=True,
)


def _configure_logging(verbose: bool) -> None:
    """Set up root logging: ``INFO`` under ``--verbose``, else ``WARNING``."""
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )


def _load_settings(*, dry_run: bool) -> Settings:
    """Load :class:`Settings` or raise a friendly :class:`typer.Exit`.

    ``dry_run=True`` injects a throwaway ``LLM_API_KEY`` if one is not
    configured, because the LLM is not called in that mode. Outside of
    dry-run a missing key is a hard error -- the pipeline would fail
    mid-flight with an opaque 401 otherwise.
    """
    try:
        return Settings()
    except ValidationError as exc:
        if dry_run:
            return Settings(llm_api_key="dry-run-placeholder")
        typer.echo(
            "Erro: LLM_API_KEY não configurada no .env (ou use --dry-run).",
            err=True,
        )
        raise typer.Exit(code=1) from exc


@app.command("scan")
def scan(
    log_path: Annotated[
        Path,
        typer.Argument(..., help="Caminho do arquivo de log a analisar."),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "-o",
            "--output",
            help="Grava o relatório Markdown neste arquivo (padrão: stdout).",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Pula o Explainer (LLM) e usa placeholders; dispensa LLM_API_KEY.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "-v",
            "--verbose",
            help="Habilita logs INFO para acompanhar o pipeline estágio a estágio.",
        ),
    ] = False,
) -> None:
    """Analisa um arquivo de log e produz um relatório de triagem em Markdown."""
    _configure_logging(verbose)

    if not log_path.is_file():
        typer.echo(f"Erro: arquivo não encontrado: {log_path}", err=True)
        raise typer.Exit(code=2)

    settings = _load_settings(dry_run=dry_run)

    try:
        markdown = asyncio.run(
            run_pipeline(log_path, settings, dry_run=dry_run),
        )
    except FileNotFoundError as exc:
        typer.echo(f"Erro: arquivo não encontrado: {exc.filename}", err=True)
        raise typer.Exit(code=2) from exc
    except AuthenticationError as exc:
        typer.echo(f"Erro de autenticação no provedor LLM: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except APITimeoutError as exc:
        typer.echo(f"Timeout ao consultar o LLM: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except ValidationError as exc:
        typer.echo(f"Erro de configuração: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.echo(f"Erro inesperado: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if output is None:
        typer.echo(markdown)
    else:
        output.write_text(markdown, encoding="utf-8")
        typer.echo(f"Relatório gravado em: {output}", err=True)


@app.command("version")
def version_cmd() -> None:
    """Imprime a versão do LST."""
    typer.echo(f"lst {__version__}")

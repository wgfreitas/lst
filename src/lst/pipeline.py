"""Pipeline orchestrator: wire all five stages into one async function.

The orchestrator is deliberately thin -- every real transformation lives
in a dedicated module (Parser+Miner, Aggregator, Detector, Explainer,
Reporter). Keeping :func:`run_pipeline` a straight sequence of calls
makes the data flow auditable at a glance and concentrates the one
externally-visible surface of the project in one place.

Policy decisions that *do* live here:

* **Dry-run mode** -- when ``dry_run=True``, the LLM call is skipped and
  each :class:`FlaggedEvent` is paired with a placeholder
  :class:`ExplainedEvent`. This path never touches the network and never
  instantiates the :class:`OpenAICompatClient`, so it works without an
  API key. Rationale: CI smoke tests, local development iterations, and
  analysts who want to validate the deterministic pipeline before
  spending tokens all share the same flow.
* **Lazy client construction** -- production callers pass
  ``client=None`` and the orchestrator builds an
  :class:`OpenAICompatClient` only when it is about to be used. Tests
  inject a :class:`LLMClient` directly, so they never touch
  :class:`Settings` for credentials.
* **No I/O on the return path** -- the function returns a Markdown
  string; writing to disk or stdout is the CLI's job. This keeps
  :func:`run_pipeline` trivially reusable from notebooks, web servers,
  or future integration tests.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from lst.aggregator import aggregate
from lst.config import Settings
from lst.detector import detect
from lst.explainer.client import LLMClient, OpenAICompatClient
from lst.explainer.engine import explain
from lst.parser import iter_log_lines, mine_templates
from lst.reporter import render
from lst.schemas import ExplainedEvent, FlaggedEvent, Severity

logger = logging.getLogger(__name__)

_DRY_RUN_MODEL = "dry-run"
_DRY_RUN_EXPLANATION = "[dry-run] explicação não gerada"
_DRY_RUN_NEXT_ACTION = "[dry-run] ação não sugerida"


async def run_pipeline(
    log_path: Path,
    settings: Settings,
    *,
    client: LLMClient | None = None,
    dry_run: bool = False,
) -> str:
    """Run the full five-stage pipeline and return the Markdown report.

    Stages are chained sequentially:

    1. :func:`lst.parser.iter_log_lines` -- stream the log file.
    2. :func:`lst.parser.mine_templates` -- drain3 clustering + per-line
       IP/user extraction.
    3. :func:`lst.aggregator.aggregate` -- rates, peaks, and cardinalities.
    4. :func:`lst.detector.detect` -- deterministic rule evaluation.
    5. :func:`lst.explainer.explain` (or the dry-run placeholder) --
       LLM-produced explanation, severity, and next action.
    6. :func:`lst.reporter.render` -- pt-BR Markdown report.

    Args:
        log_path: Path to the log file to analyse. Must exist and be a
            regular file.
        settings: Runtime configuration. Used for the LLM model name and,
            when ``client`` is ``None`` and ``dry_run`` is ``False``, to
            construct the default :class:`OpenAICompatClient`.
        client: Optional pre-built :class:`LLMClient`. Tests inject a
            fake here; production callers leave it ``None``.
        dry_run: When ``True``, the Explainer stage is replaced by a
            placeholder that emits a neutral :class:`ExplainedEvent` per
            flagged event. No LLM calls are made, so no API key is
            required.

    Returns:
        The rendered Markdown report, ready to be written to stdout or a
        file.

    Raises:
        FileNotFoundError: if ``log_path`` does not point at a regular
            file. Propagates unchanged from the Parser stage.
        openai.AuthenticationError: if the live LLM rejects the API key.
        openai.APITimeoutError: if the LLM request exceeds the configured
            timeout.

    Example:
        >>> import asyncio
        >>> from pathlib import Path
        >>> from lst.config import Settings
        >>> from lst.pipeline import run_pipeline
        >>> markdown = asyncio.run(
        ...     run_pipeline(Path("auth.log"), Settings(), dry_run=True)
        ... )
        >>> markdown.startswith("# Relatório de Triagem de Logs")
        True
    """
    logger.info("Pipeline started: %s", log_path)

    lines = list(iter_log_lines(log_path))
    logger.info("Stage 1 (Parser reader) complete: %d lines", len(lines))

    templates, mined_lines = mine_templates(lines)
    logger.info(
        "Stage 2 (Template miner) complete: %d templates, %d mined lines",
        len(templates),
        len(mined_lines),
    )

    aggregated = aggregate(templates, mined_lines)
    logger.info("Stage 3 (Aggregator) complete: %d aggregated templates", len(aggregated))

    flagged = detect(aggregated)
    logger.info("Stage 4 (Detector) complete: %d flagged events", len(flagged))

    if dry_run:
        explained = _dry_run_explain(flagged)
        logger.info("Stage 5 (Explainer) skipped (dry-run): %d placeholders", len(explained))
    else:
        active_client = client if client is not None else OpenAICompatClient(settings)
        explained = await explain(
            flagged,
            active_client,
            model=settings.llm_model,
        )
        logger.info("Stage 5 (Explainer) complete: %d explained events", len(explained))

    markdown = render(
        explained,
        source_path=log_path,
        generated_at=datetime.now(UTC),
    )
    logger.info(
        "Pipeline complete: %d flagged, %d explained",
        len(flagged),
        len(explained),
    )
    return markdown


def _dry_run_explain(flagged: list[FlaggedEvent]) -> list[ExplainedEvent]:
    """Produce neutral :class:`ExplainedEvent` placeholders without an LLM."""
    now = datetime.now(UTC)
    return [
        ExplainedEvent(
            flagged=event,
            explanation=_DRY_RUN_EXPLANATION,
            severity=Severity.MEDIUM,
            next_action=_DRY_RUN_NEXT_ACTION,
            llm_model=_DRY_RUN_MODEL,
            llm_latency_ms=0,
            explained_at=now,
        )
        for event in flagged
    ]

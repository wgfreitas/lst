"""Render a triage-ready Markdown report from explained events.

The output is designed to be read top-to-bottom by a SOC/ETIR analyst:

* A small metadata header with the source path, generation timestamp, and
  total event count.
* A severity-distribution block (emoji + counts) so the reviewer can see
  at a glance how alarming the batch is. Dropped when the report is
  empty -- a block saying "0 criticos, 0 altos..." is noise.
* One section per event, ordered by severity descending and then by the
  Detector score descending. Each section carries a stats table, the
  LLM's explanation, its suggested next action, and up to three raw
  sample lines so the analyst has grounding without opening another
  file.
* An appendix listing the active detection rules and their purpose,
  derived by iterating :data:`ACTIVE_RULES` so new rules appear without
  editing this module.

Deliberate choices worth calling out:

* Only the summary distribution block uses emoji (🔴🟠🟡🟢). The event
  bodies stay plain text so the report stays grep-friendly and diffs
  cleanly for anyone reviewing output over email or a terminal pager.
* Category in the event header uses the ``FlagCategory`` value (the
  snake_case identifier) rather than the pt-BR label. Keeping the
  technical identifier in the header makes cross-referencing an event
  with a Detector rule trivial; the pt-BR label shows up in the body.
* Long text is truncated with an ellipsis: templates at
  :data:`_MAX_TEMPLATE_HEADER_LENGTH` characters, sample lines at
  :data:`_MAX_SAMPLE_LINE_LENGTH`. The cuts keep the report from
  ballooning when drain3 captures verbose multi-KB lines.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from lst.detector.rules import ACTIVE_RULES
from lst.detector.rules.base import Rule
from lst.schemas import ExplainedEvent, FlagCategory, Severity

_SEVERITY_LABEL_PT: dict[Severity, str] = {
    Severity.CRITICAL: "Crítico",
    Severity.HIGH: "Alto",
    Severity.MEDIUM: "Médio",
    Severity.LOW: "Baixo",
}

_CATEGORY_LABEL_PT: dict[FlagCategory, str] = {
    FlagCategory.NOVELTY: "Novidade",
    FlagCategory.BRUTE_FORCE: "Brute Force",
    FlagCategory.SPIKE: "Pico de taxa",
    FlagCategory.HIGH_RISK_PATTERN: "Padrão de alto risco",
    FlagCategory.VARIETY: "Variedade de fontes",
}

_SEVERITY_EMOJI: dict[Severity, str] = {
    Severity.CRITICAL: "🔴",
    Severity.HIGH: "🟠",
    Severity.MEDIUM: "🟡",
    Severity.LOW: "🟢",
}

_SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 3,
    Severity.HIGH: 2,
    Severity.MEDIUM: 1,
    Severity.LOW: 0,
}

_SEVERITY_ORDER: tuple[Severity, ...] = (
    Severity.CRITICAL,
    Severity.HIGH,
    Severity.MEDIUM,
    Severity.LOW,
)

_MAX_TEMPLATE_HEADER_LENGTH = 120
_MAX_SAMPLE_LINE_LENGTH = 120
_MAX_SAMPLE_LINES_PER_EVENT = 3


def render(
    events: list[ExplainedEvent],
    *,
    source_path: Path | str,
    generated_at: datetime,
) -> str:
    """Render the final pt-BR Markdown report.

    Args:
        events: Explained events produced by the Explainer stage. May be
            empty, in which case the report becomes a short placeholder
            followed by the rules appendix.
        source_path: Path of the log file (or logical source) that was
            analysed. Only used as text in the header; no I/O happens.
        generated_at: UTC timestamp stamped into the header so the
            report is self-describing.

    Returns:
        A single Markdown string. The return value is the full report;
        callers decide whether to print it, write it to disk, or attach
        it to a ticket.
    """
    if not events:
        return _render_empty_report(source_path=source_path, generated_at=generated_at)

    ordered = sorted(
        events,
        key=lambda e: (_severity_rank(e.severity), e.flagged.score),
        reverse=True,
    )

    sections: list[str] = [
        _render_header(
            source_path=source_path,
            generated_at=generated_at,
            total=len(ordered),
        ),
        _render_summary_block(ordered),
        _render_events_block(ordered),
        _render_rules_appendix(ACTIVE_RULES),
    ]
    return "\n\n".join(sections) + "\n"


def _render_empty_report(*, source_path: Path | str, generated_at: datetime) -> str:
    """Short placeholder when the pipeline produced no explained events."""
    header = _render_header(source_path=source_path, generated_at=generated_at, total=0)
    placeholder = "## Resumo\n\nNenhum evento suspeito foi identificado na janela analisada."
    appendix = _render_rules_appendix(ACTIVE_RULES)
    return "\n\n".join([header, placeholder, appendix]) + "\n"


def _render_header(
    *,
    source_path: Path | str,
    generated_at: datetime,
    total: int,
) -> str:
    """Top-of-file metadata: title, source, timestamp, event count."""
    return (
        "# Relatório de Triagem de Logs\n\n"
        f"- **Fonte**: `{source_path}`\n"
        f"- **Gerado em**: {generated_at.isoformat()}\n"
        f"- **Total de eventos**: {total}"
    )


def _render_summary_block(events: list[ExplainedEvent]) -> str:
    """Distribution line with one entry per severity, in descending order."""
    counter: Counter[Severity] = Counter(e.severity for e in events)
    lines = ["## Resumo por severidade", ""]
    for severity in _SEVERITY_ORDER:
        emoji = _SEVERITY_EMOJI[severity]
        label = _SEVERITY_LABEL_PT[severity]
        count = counter.get(severity, 0)
        lines.append(f"- {emoji} **{label}**: {count}")
    return "\n".join(lines)


def _render_events_block(events: list[ExplainedEvent]) -> str:
    """Join per-event sections; caller ensures ``events`` is already sorted."""
    return "\n\n".join(
        _render_event(event, index=index) for index, event in enumerate(events, start=1)
    )


def _render_event(event: ExplainedEvent, *, index: int) -> str:
    """Render a single explained event to Markdown."""
    flagged = event.flagged
    aggregated = flagged.aggregated
    template = aggregated.template

    header_template = _truncate(template.template, _MAX_TEMPLATE_HEADER_LENGTH)
    header = (
        f"## {index}. [{event.severity.value.upper()}] "
        f"{flagged.category.value}: {header_template}"
    )

    meta = (
        f"- **Severidade**: {_SEVERITY_LABEL_PT[event.severity]}\n"
        f"- **Categoria**: {_CATEGORY_LABEL_PT[flagged.category]}\n"
        f"- **Regra**: `{flagged.rule_name}` (score {flagged.score:.2f})\n"
        f"- **Janela**: {template.first_seen.isoformat()} → "
        f"{template.last_seen.isoformat()}"
    )

    stats = _render_stats_table(event)
    explanation = f"### Explicação\n\n{event.explanation}"
    next_action = f"### Próxima ação\n\n{event.next_action}"
    samples = _render_samples(template.sample_lines)

    return "\n\n".join([header, meta, stats, explanation, next_action, samples])


def _render_stats_table(event: ExplainedEvent) -> str:
    """Compact Markdown table of the Aggregator-derived metrics."""
    aggregated = event.flagged.aggregated
    ips_preview = _format_sample_list(aggregated.sample_ips)
    users_preview = _format_sample_list(aggregated.sample_users)
    return (
        "### Métricas\n\n"
        "| Métrica | Valor |\n"
        "| --- | --- |\n"
        f"| Ocorrências totais | {aggregated.total_count} |\n"
        f"| Taxa média (por minuto) | {aggregated.rate_per_minute:.2f} |\n"
        f"| Pico (por minuto) | {aggregated.peak_rate_per_minute:.2f} |\n"
        f"| IPs únicos | {aggregated.unique_ips} |\n"
        f"| Usuários únicos | {aggregated.unique_users} |\n"
        f"| Amostra de IPs | {ips_preview} |\n"
        f"| Amostra de usuários | {users_preview} |"
    )


def _render_samples(sample_lines: list[str]) -> str:
    """Numbered list of up to three raw sample lines, each truncated."""
    if not sample_lines:
        return "### Linhas originais\n\n(nenhuma)"
    shown = sample_lines[:_MAX_SAMPLE_LINES_PER_EVENT]
    body = "\n".join(
        f"{index}. `{_truncate(line, _MAX_SAMPLE_LINE_LENGTH)}`"
        for index, line in enumerate(shown, start=1)
    )
    return "### Linhas originais\n\n" + body


def _render_rules_appendix(rules: Iterable[Rule]) -> str:
    """Bulleted list of active detection rules, derived from ACTIVE_RULES."""
    lines = ["## Apêndice: regras de detecção ativas", ""]
    for rule in rules:
        lines.append(f"- **`{rule.name}`** ({rule.category.value}) — {rule.description_pt}")
    return "\n".join(lines)


def _format_sample_list(values: list[str]) -> str:
    """Return ``(nenhum)`` or a backtick-wrapped comma-joined preview."""
    if not values:
        return "(nenhum)"
    return ", ".join(f"`{value}`" for value in values)


def _truncate(text: str, max_length: int) -> str:
    """Return ``text`` with an ellipsis when it exceeds ``max_length``."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def _severity_rank(severity: Severity) -> int:
    """Integer rank used by the sort key (higher = more severe)."""
    return _SEVERITY_RANK[severity]

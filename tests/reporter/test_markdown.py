"""Unit tests for :func:`lst.reporter.markdown.render`.

The Reporter is a pure function: tests assert on the exact Markdown
string returned. Style note: prefer ``in`` checks over full-string
equality so the tests remain robust when surrounding formatting (emoji
variant, extra whitespace, header wording) evolves without changing
meaning.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from lst.detector.rules import ACTIVE_RULES
from lst.reporter import render
from lst.schemas import ExplainedEvent, FlagCategory, Severity

_GENERATED_AT = datetime(2026, 4, 18, 11, 0, 0, tzinfo=UTC)
_SOURCE_PATH = Path("/var/log/auth.log")


def test_render_returns_header_with_source_and_timestamp(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """Report starts with the title, source path, and ISO-formatted timestamp."""
    out = render(
        [make_explained()],
        source_path=_SOURCE_PATH,
        generated_at=_GENERATED_AT,
    )
    assert out.startswith("# Relatório de Triagem de Logs")
    assert "/var/log/auth.log" in out
    assert _GENERATED_AT.isoformat() in out
    assert "Total de eventos**: 1" in out


def test_render_orders_events_by_severity_descending(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """CRITICAL comes before HIGH comes before MEDIUM comes before LOW."""
    events = [
        make_explained(cluster_id=1, severity=Severity.LOW, score=0.1),
        make_explained(cluster_id=2, severity=Severity.CRITICAL, score=0.5),
        make_explained(cluster_id=3, severity=Severity.MEDIUM, score=0.3),
        make_explained(cluster_id=4, severity=Severity.HIGH, score=0.4),
    ]
    out = render(events, source_path=_SOURCE_PATH, generated_at=_GENERATED_AT)

    critical_pos = out.index("[CRITICAL]")
    high_pos = out.index("[HIGH]")
    medium_pos = out.index("[MEDIUM]")
    low_pos = out.index("[LOW]")

    assert critical_pos < high_pos < medium_pos < low_pos


def test_render_ties_broken_by_score_descending(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """Same severity -> higher score renders first."""
    lower = make_explained(
        cluster_id=10,
        severity=Severity.HIGH,
        score=0.5,
        template="Template com score menor <*>",
    )
    higher = make_explained(
        cluster_id=11,
        severity=Severity.HIGH,
        score=0.95,
        template="Template com score maior <*>",
    )
    out = render(
        [lower, higher],
        source_path=_SOURCE_PATH,
        generated_at=_GENERATED_AT,
    )
    assert out.index("Template com score maior") < out.index("Template com score menor")


def test_render_empty_list_returns_placeholder_without_distribution(
    # no events fixture needed
) -> None:
    """Empty input -> short message, no emoji distribution block, rules appendix stays."""
    out = render([], source_path=_SOURCE_PATH, generated_at=_GENERATED_AT)
    assert "Nenhum evento suspeito" in out
    assert "Resumo por severidade" not in out
    assert "Apêndice" in out
    for rule in ACTIVE_RULES:
        assert rule.name in out


def test_render_summary_block_uses_emojis_and_counts(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """All four severity emojis appear with accurate counts."""
    events = [
        make_explained(cluster_id=1, severity=Severity.CRITICAL),
        make_explained(cluster_id=2, severity=Severity.CRITICAL),
        make_explained(cluster_id=3, severity=Severity.HIGH),
        make_explained(cluster_id=4, severity=Severity.MEDIUM),
    ]
    out = render(events, source_path=_SOURCE_PATH, generated_at=_GENERATED_AT)
    assert "🔴" in out and "**Crítico**: 2" in out
    assert "🟠" in out and "**Alto**: 1" in out
    assert "🟡" in out and "**Médio**: 1" in out
    assert "🟢" in out and "**Baixo**: 0" in out


def test_render_emoji_only_in_summary_not_in_event_bodies(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """Event sections stay emoji-free so bodies remain grep/diff friendly."""
    events = [
        make_explained(cluster_id=1, severity=Severity.CRITICAL),
        make_explained(cluster_id=2, severity=Severity.HIGH),
    ]
    out = render(events, source_path=_SOURCE_PATH, generated_at=_GENERATED_AT)

    summary_start = out.index("## Resumo por severidade")
    events_start = out.index("## 1.")
    summary_block = out[summary_start:events_start]
    events_block = out[events_start:]

    assert "🔴" in summary_block
    for emoji in ("🔴", "🟠", "🟡", "🟢"):
        assert emoji not in events_block


def test_render_event_header_truncates_long_template(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """A 200-char template is cut to 120 with a trailing ellipsis."""
    long_template = "A" * 200
    out = render(
        [make_explained(template=long_template)],
        source_path=_SOURCE_PATH,
        generated_at=_GENERATED_AT,
    )
    assert "A" * 117 + "..." in out
    assert "A" * 200 not in out


def test_render_preserves_break_in_attempt_in_header(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """A <=120-char template ending in 'POSSIBLE BREAK-IN ATTEMPT!' is not truncated."""
    template = (
        "reverse mapping checking getaddrinfo for malicious.example.com "
        "failed - POSSIBLE BREAK-IN ATTEMPT!"
    )
    assert len(template) <= 120
    out = render(
        [make_explained(template=template)],
        source_path=_SOURCE_PATH,
        generated_at=_GENERATED_AT,
    )
    assert "POSSIBLE BREAK-IN ATTEMPT!" in out
    assert "POSSIBLE BREAK-IN ATT..." not in out
    assert "POSSI..." not in out


def test_render_event_truncates_long_sample_line(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """Sample lines over 120 chars are cut to 120 with a trailing ellipsis."""
    long_sample = "B" * 200
    out = render(
        [make_explained(sample_lines=[long_sample])],
        source_path=_SOURCE_PATH,
        generated_at=_GENERATED_AT,
    )
    assert "B" * 117 + "..." in out
    assert "B" * 200 not in out


def test_render_event_header_uses_category_value_not_pt_label(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """Event header carries the technical snake_case category, not the pt-BR label."""
    out = render(
        [make_explained(category=FlagCategory.BRUTE_FORCE, severity=Severity.HIGH)],
        source_path=_SOURCE_PATH,
        generated_at=_GENERATED_AT,
    )
    assert "[HIGH] brute_force:" in out


def test_render_event_body_uses_pt_labels_for_severity_and_category(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """Body surfaces the pt-BR labels so analysts read natural language."""
    out = render(
        [make_explained(category=FlagCategory.BRUTE_FORCE, severity=Severity.HIGH)],
        source_path=_SOURCE_PATH,
        generated_at=_GENERATED_AT,
    )
    assert "**Severidade**: Alto" in out
    assert "**Categoria**: Brute Force" in out


def test_render_singleton_hides_rate_numbers(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """total_count==1 renders '— (evento único)' instead of '1.00' rate."""
    event = make_explained(
        total_count=1,
        rate_per_minute=1.0,
        peak_rate_per_minute=1.0,
        sample_lines=["Failed password for root from 203.0.113.10 port 22 ssh2"],
    )
    out = render(
        [event],
        source_path=_SOURCE_PATH,
        generated_at=_GENERATED_AT,
    )
    stats_section = out.split("### Métricas")[1].split("###")[0]
    assert "1.00" not in stats_section
    assert stats_section.count("— (evento único)") == 2


def test_render_multi_event_keeps_numeric_rate(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """total_count>1 keeps numeric rates; singleton marker stays absent."""
    event = make_explained(
        total_count=20,
        rate_per_minute=0.67,
        peak_rate_per_minute=2.00,
    )
    out = render(
        [event],
        source_path=_SOURCE_PATH,
        generated_at=_GENERATED_AT,
    )
    assert "0.67" in out
    assert "2.00" in out
    assert "— (evento único)" not in out


def test_render_event_metrics_table_includes_expected_values(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """Per-event stats table surfaces total_count, rate, peak, and cardinalities."""
    out = render(
        [
            make_explained(
                total_count=42,
                rate_per_minute=1.5,
                peak_rate_per_minute=6.0,
                unique_ips=30,
                unique_users=4,
            )
        ],
        source_path=_SOURCE_PATH,
        generated_at=_GENERATED_AT,
    )
    assert "| Ocorrências totais | 42 |" in out
    assert "| Taxa média (por minuto) | 1.50 |" in out
    assert "| Pico (por minuto) | 6.00 |" in out
    assert "| IPs únicos | 30 |" in out
    assert "| Usuários únicos | 4 |" in out


def test_render_event_explanation_and_next_action_appear_verbatim(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """The LLM's explanation and next_action render verbatim in the body."""
    event = make_explained(
        explanation="Tentativa de força bruta contra SSH detectada.",
        next_action="Bloquear IPs ofensivos no firewall de borda.",
    )
    out = render([event], source_path=_SOURCE_PATH, generated_at=_GENERATED_AT)
    assert "Tentativa de força bruta contra SSH detectada." in out
    assert "Bloquear IPs ofensivos no firewall de borda." in out


def test_render_appendix_lists_every_active_rule(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """The appendix iterates ACTIVE_RULES so adding a rule never updates this module."""
    out = render(
        [make_explained()],
        source_path=_SOURCE_PATH,
        generated_at=_GENERATED_AT,
    )
    assert "## Apêndice: regras de detecção ativas" in out
    for rule in ACTIVE_RULES:
        assert rule.name in out
        assert rule.description_pt in out


def test_render_accepts_source_path_as_string(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """``source_path`` may be a plain string; the header carries it verbatim."""
    out = render(
        [make_explained()],
        source_path="remote://sftp/logs/auth.log",
        generated_at=_GENERATED_AT,
    )
    assert "remote://sftp/logs/auth.log" in out


def test_render_generated_at_is_formatted_as_iso(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """The generated_at timestamp is rendered as ISO-8601 (including TZ)."""
    out = render(
        [make_explained()],
        source_path=_SOURCE_PATH,
        generated_at=_GENERATED_AT,
    )
    assert "2026-04-18T11:00:00+00:00" in out


def test_render_event_shows_rule_name_and_score(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """Each event surfaces the Detector rule id and score for audit trails."""
    out = render(
        [make_explained(rule_name="brute_force_by_ip_cardinality", score=0.87)],
        source_path=_SOURCE_PATH,
        generated_at=_GENERATED_AT,
    )
    assert "`brute_force_by_ip_cardinality`" in out
    assert "score 0.87" in out


def test_render_event_numbers_are_sequential(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """Per-event section headers are numbered starting from 1."""
    events = [
        make_explained(cluster_id=1, severity=Severity.HIGH, score=0.9),
        make_explained(cluster_id=2, severity=Severity.MEDIUM, score=0.5),
        make_explained(cluster_id=3, severity=Severity.LOW, score=0.2),
    ]
    out = render(events, source_path=_SOURCE_PATH, generated_at=_GENERATED_AT)
    assert "## 1." in out
    assert "## 2." in out
    assert "## 3." in out
    assert "## 4." not in out


def test_render_lists_discarded_events_in_footer(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """Non-empty ``discarded`` adds a footer table with cluster, category, rule, score."""
    explained = make_explained(cluster_id=1, severity=Severity.HIGH)
    discarded = [
        make_explained(
            cluster_id=5,
            category=FlagCategory.HIGH_RISK_PATTERN,
            rule_name="high_risk_keyword_match",
            score=0.9,
        ).flagged
    ]
    out = render(
        [explained],
        source_path=_SOURCE_PATH,
        generated_at=_GENERATED_AT,
        discarded=discarded,
    )
    assert "## Eventos não explicados" in out
    assert "investigação manual" in out
    assert "| 5 | Padrão de alto risco | `high_risk_keyword_match` | 0.90 |" in out


def test_render_omits_discarded_section_when_none(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """Default ``discarded=None`` keeps the report clean (no footer)."""
    out = render([make_explained()], source_path=_SOURCE_PATH, generated_at=_GENERATED_AT)
    assert "Eventos não explicados" not in out


def test_render_omits_discarded_section_when_empty(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """An explicit empty ``discarded`` list also omits the footer."""
    out = render(
        [make_explained()],
        source_path=_SOURCE_PATH,
        generated_at=_GENERATED_AT,
        discarded=[],
    )
    assert "Eventos não explicados" not in out


def test_render_discarded_footer_shown_when_all_events_discarded(
    make_explained: Callable[..., ExplainedEvent],
) -> None:
    """No explained events but some discarded -> footer shown, not 'nada suspeito'."""
    discarded = [
        make_explained(
            cluster_id=7,
            category=FlagCategory.SPIKE,
            rule_name="spike_zscore",
            score=0.75,
        ).flagged
    ]
    out = render(
        [],
        source_path=_SOURCE_PATH,
        generated_at=_GENERATED_AT,
        discarded=discarded,
    )
    assert "## Eventos não explicados" in out
    assert "| 7 | Pico de taxa | `spike_zscore` | 0.75 |" in out
    assert "Nenhum evento suspeito" not in out
    assert "Apêndice" in out

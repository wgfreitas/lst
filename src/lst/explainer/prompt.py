"""Build ``(system, user)`` message pairs for the LLM Explainer.

Both prompts are produced from a single :class:`FlaggedEvent` so the
rest of the Explainer never reaches back into the schema. The function
is pure -- no I/O, no logging -- which keeps testing cheap and lets the
Reporter audit the exact bytes sent to the model for each event.

Design notes:

* The system prompt is a module-level constant so reviewers can read
  it without scrolling through orchestration code. It is in pt-BR by
  design -- mixing languages in the system message leaks into the
  model's output.
* The user prompt is markdown for readability in logs, not because the
  model needs markdown. Bullets + headings keep the payload terse
  (~300-500 tokens per event) and stable across fields.
* IP and user samples are capped at three entries. Typical sample_ips
  already contains five, but for token economy three is enough to
  convey the shape ("single IP" vs "distributed fan-in").
"""

from __future__ import annotations

from lst.schemas import FlaggedEvent

_SYSTEM_PROMPT_PT = """\
Você é um analista sênior de SOC revisando eventos de segurança.
Para cada evento recebido, produza estritamente um JSON com os campos:
- "explanation": 1-2 frases explicando o que o evento indica
- "severity": exatamente um de ["low", "medium", "high", "critical"]
- "next_action": 1 frase com a próxima ação investigativa

Responda SOMENTE com o JSON, sem texto antes ou depois, sem markdown
fences, sem comentários. Todas as strings em português brasileiro."""

_SAMPLE_PREFIX_LIMIT = 3


def build_messages(event: FlaggedEvent) -> tuple[str, str]:
    """Return the ``(system, user)`` prompt pair for a :class:`FlaggedEvent`.

    Args:
        event: A flagged event emitted by the Detector stage.

    Returns:
        A 2-tuple ``(system_prompt, user_prompt)`` ready to be passed to
        the LLM client's ``chat.completions.create`` call.
    """
    aggregated = event.aggregated
    template = aggregated.template

    ips_sample = _format_sample(aggregated.sample_ips)
    users_sample = _format_sample(aggregated.sample_users)
    notes = event.context_notes if event.context_notes else "(nenhuma)"

    sample_lines_numbered = "\n".join(
        f"{index}. {raw_line}" for index, raw_line in enumerate(template.sample_lines, start=1)
    )

    user_prompt = f"""\
## Evento flagado pelo Detector

- **Template**: {template.template}
- **Categoria**: {event.category.value}
- **Regra disparada**: {event.rule_name}
- **Score**: {event.score:.2f}
- **Ocorrências totais**: {aggregated.total_count}
- **IPs únicos**: {aggregated.unique_ips} (amostra: {ips_sample})
- **Usuários únicos**: {aggregated.unique_users} (amostra: {users_sample})
- **Taxa média**: {aggregated.rate_per_minute:.2f}/min
- **Pico**: {aggregated.peak_rate_per_minute:.1f}/min
- **Janela**: {template.first_seen.isoformat()} → {template.last_seen.isoformat()}
- **Observações do Detector**: {notes}

### Exemplos de linhas originais
{sample_lines_numbered}"""

    return _SYSTEM_PROMPT_PT, user_prompt


def _format_sample(values: list[str]) -> str:
    """Return a compact ``[a, b, c]`` literal capped at three entries."""
    if not values:
        return "[]"
    trimmed = values[:_SAMPLE_PREFIX_LIMIT]
    return "[" + ", ".join(trimmed) + "]"

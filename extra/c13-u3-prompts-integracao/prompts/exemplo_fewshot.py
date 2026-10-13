"""Exemplo: teste de integração do LST com o provedor de LLM simulado por respx."""

from __future__ import annotations

from pathlib import Path

import httpx
import respx

from lst.config import Settings
from lst.pipeline import run_pipeline

FIXTURE = Path("tests/fixtures/auth_sample.log")
ENDPOINT = "https://llm.test/v1/chat/completions"
VALID_REPLY = (
    '{"explanation": "Força bruta contra SSH a partir de vários IPs.", '
    '"severity": "high", "next_action": "Bloquear os IPs no firewall."}'
)


def make_settings(**overrides: object) -> Settings:
    """Configuração isolada: ignora o .env local e aponta para o servidor simulado."""
    values: dict[str, object] = {
        "llm_api_key": "fake-key",
        "llm_model": "fake-model",
        "llm_base_url": "https://llm.test/v1",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def chat_completion(content: str) -> httpx.Response:
    """Resposta 200 no formato chat.completion com o conteúdo dado."""
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-fake",
            "object": "chat.completion",
            "created": 0,
            "model": "fake-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
        },
    )


async def test_valid_reply_for_each_flagged_event_produces_full_report() -> None:
    """Regra: uma requisição por evento marcado; respostas válidas geram o relatório sem rodapé."""
    with respx.mock(assert_all_called=True) as router:
        route = router.post(ENDPOINT).mock(return_value=chat_completion(VALID_REPLY))
        report = await run_pipeline(FIXTURE, make_settings())

    assert route.call_count == 3
    assert report.startswith("# Relatório de Triagem de Logs")
    assert report.count("### Próxima ação") == 3
    assert "## Eventos não explicados" not in report

```python
# tests/test_llm_integration.py: somente os trechos alterados.
#
# Diagnóstico das 7 falhas:
# 1) test_timeout_configurado_vale_para_cada_chamada[limite-inferior|limite-superior]: o erro era do TESTE.
#    O oráculo exigia um detalhe de implementação que o contrato não pede (timeout de leitura do httpx igual a
#    LLM_TIMEOUT_SECONDS); o LST pode aplicar o prazo em outra camada, como o asyncio. Troquei por testes de
#    comportamento com um servidor lento simulado. Como o respx substitui a camada de rede, a simulação também
#    reproduz o timeout de leitura que o cliente HTTP pede. Mas o valor observado (leitura sempre em 60 s,
#    qualquer que seja a configuração) mostra um defeito real no limite superior: com LLM_TIMEOUT_SECONDS=300,
#    a chamada é cortada em 60 s. Esse caso ficou como xfail estrito, sem mudar o oráculo do contrato.
# 2) test_corpo_200_fora_do_formato_chat_completion_vira_evento_nao_explicado (5 casos): falhas VERDADEIRAS.
#    Pelo contrato, "200 OK com resposta vazia ou inválida" gera novas requisições e o evento vai para
#    "## Eventos não explicados". O LST, em vez disso, deixa escapar exceções não tratadas (client.py:210).
#    Não afrouxei o oráculo para aceitar a exceção. Marquei os casos com xfail estrito, limitado à exceção
#    observada (raises=...). Quando o defeito for corrigido, o XPASS(strict) vai indicar que a marca deve sair.


# ======================================================================================
# NOVO: colocar na seção "Funções auxiliares", ANTES das listas de partições.
# ======================================================================================

ESPERA_REAL_MAXIMA = 2.0  # atrasos simulados acima disso são comprimidos (tempo virtual)


def servidor_lento(atraso: float) -> Callable[[httpx.Request], Any]:
    """Simula um modelo que leva `atraso` segundos para devolver 200 válido.

    O respx substitui a camada de rede, então a simulação faz o papel do transporte real: se o timeout de
    leitura pedido pelo cliente HTTP for menor que o atraso, lança httpx.ReadTimeout. Atrasos acima de
    ESPERA_REAL_MAXIMA são comprimidos. Isso só vale nos cenários em que nenhum prazo do LST deve vencer antes.
    """
    contador = iter(range(10_000))

    async def responder(request: httpx.Request) -> httpx.Response:
        leitura = request.extensions.get("timeout", {}).get("read")
        if leitura is not None and leitura < atraso:
            await asyncio.sleep(min(leitura, ESPERA_REAL_MAXIMA))
            raise httpx.ReadTimeout(
                "Simulação: o modelo não respondeu dentro do timeout de leitura.", request=request
            )
        await asyncio.sleep(atraso if atraso <= ESPERA_REAL_MAXIMA else 0.01)
        return resposta_valida(next(contador))

    return responder


def defeito_do_lst(excecao: type[BaseException], detalhe: str) -> pytest.MarkDecorator:
    """Marca um caso que falha por defeito confirmado do LST, sem mudar o oráculo do contrato."""
    return pytest.mark.xfail(strict=True, raises=excecao, reason=f"Defeito do LST: {detalhe}")


# ======================================================================================
# SUBSTITUI a lista CORPOS_200_INVALIDOS. A função de teste que usa a lista continua igual.
# ======================================================================================

_SEM_TRATAMENTO = (
    "exceção não tratada em src/lst/explainer/client.py:210, quando o contrato exige nova requisição "
    "(LLM_PARSE_RETRIES) e o evento em '## Eventos não explicados'"
)

CORPOS_200_INVALIDOS = [
    pytest.param(
        lambda: httpx.Response(200, json={**chat_completion(None), "choices": []}),
        id="choices-vazio",
        marks=defeito_do_lst(IndexError, f"200 com choices vazio gera IndexError; {_SEM_TRATAMENTO}"),
    ),
    pytest.param(
        lambda: httpx.Response(200, json={}),
        id="objeto-vazio",
        marks=defeito_do_lst(TypeError, f"200 com corpo {{}} gera TypeError; {_SEM_TRATAMENTO}"),
    ),
    pytest.param(
        lambda: httpx.Response(200, content=b"", headers={"Content-Type": "application/json"}),
        id="corpo-vazio",
        marks=defeito_do_lst(json.JSONDecodeError, f"200 com corpo vazio gera JSONDecodeError; {_SEM_TRATAMENTO}"),
    ),
    pytest.param(
        lambda: httpx.Response(200, html="<html><body>Serviço em manutenção</body></html>"),
        id="html",
        marks=defeito_do_lst(AttributeError, f"200 com corpo HTML gera AttributeError; {_SEM_TRATAMENTO}"),
    ),
    pytest.param(
        lambda: httpx.Response(200, json={"error": {"message": "Upstream provider error", "code": 502}}),
        id="erro-dentro-de-200",
        marks=defeito_do_lst(TypeError, f"200 com objeto error gera TypeError; {_SEM_TRATAMENTO}"),
    ),
    pytest.param(
        lambda: httpx.Response(200, json=chat_completion(None, finish_reason="length")),
        id="cortado-por-max-tokens",
    ),
]


# ======================================================================================
# SUBSTITUI test_timeout_configurado_vale_para_cada_chamada. Remover a função antiga.
# ======================================================================================

DEFEITO_TIMEOUT_MAXIMO = defeito_do_lst(
    AssertionError,
    "com LLM_TIMEOUT_SECONDS=300 o cliente HTTP mantém o timeout de leitura fixo em 60 s "
    "(observado em request.extensions['timeout']); uma chamada de 299 s, dentro do prazo, é abortada como timeout",
)


def test_cli_resposta_abaixo_do_timeout_minimo_e_aceita(env_cli, rota_chat, log_calibrado):
    """Com LLM_TIMEOUT_SECONDS=1.0, um modelo que responde em 0,4 s gera o relatório completo com código 0."""
    env_cli(LLM_TIMEOUT_SECONDS="1.0", LLM_MAX_RETRIES="0")
    rota_chat.mock(side_effect=servidor_lento(0.4))
    resultado = rodar_scan(log_calibrado)
    assert_encerramento(resultado, 0)
    assert_relatorio(resultado.stdout, explicados=EVENTOS)
    assert rota_chat.call_count == EVENTOS


def test_cli_resposta_acima_do_timeout_minimo_gera_erro_de_timeout(env_cli, rota_chat, log_calibrado):
    """Com LLM_TIMEOUT_SECONDS=1.0, um modelo que demora 1,6 s gera código 1 e 'Timeout ao consultar o LLM'."""
    env_cli(LLM_TIMEOUT_SECONDS="1.0", LLM_MAX_RETRIES="0")
    rota_chat.mock(side_effect=servidor_lento(1.6))
    resultado = rodar_scan(log_calibrado)
    assert_encerramento(resultado, 1)
    assert MSG_TIMEOUT in normalizar(saida_erro(resultado))
    assert TITULO not in resultado.stdout


@pytest.mark.parametrize(
    "timeout, atraso",
    [
        pytest.param(None, 59.0, id="padrao-60s-modelo-em-59s"),
        pytest.param(300.0, 299.0, id="maximo-300s-modelo-em-299s", marks=DEFEITO_TIMEOUT_MAXIMO),
    ],
)
def test_cli_modelo_lento_dentro_do_prazo_nao_e_abortado(timeout, atraso, env_cli, rota_chat, log_calibrado):
    """Modelo que responde 1 s antes de LLM_TIMEOUT_SECONDS (padrão e máximo) não é abortado e o relatório sai completo."""
    ambiente = {"LLM_MAX_RETRIES": "0"}
    if timeout is not None:
        ambiente["LLM_TIMEOUT_SECONDS"] = str(timeout)
    env_cli(**ambiente)
    rota_chat.mock(side_effect=servidor_lento(atraso))
    resultado = rodar_scan(log_calibrado)
    assert_encerramento(resultado, 0)
    assert_relatorio(resultado.stdout, explicados=EVENTOS)
```

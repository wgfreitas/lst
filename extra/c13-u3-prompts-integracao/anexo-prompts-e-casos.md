# Anexo — prompts, casos gerados e medições

Complemento de `resposta-prompts-integracao.md`. As respostas literais do modelo estão em
`saidas/`, os prompts em `prompts/` e as ferramentas de medição em `ferramentas/`.

## 1. Ambiente e método

- **Sistema sob teste:** LST no `main` do GitHub (`fdd5bca`), Python 3.11.15, openai 2.54.0,
  httpx 0.28.1, respx 0.22.0.
- **Modelo:** `claude-opus-5-5`, confirmado pela própria sessão. Cada execução foi uma sessão nova,
  sem histórico. A única ferramenta permitida foi a leitura do arquivo com o prompt; nas três últimas
  execuções, o modelo também gravou a própria resposta em arquivo, para evitar erro de transcrição.
  A interação de correção continuou a sessão do P1 v1, como na versão interativa da unidade.
- **Execução:** os testes gerados rodaram sem nenhuma alteração. No P0, registrei o marcador
  `integration`, como o próprio modelo instruiu.
- **Gabarito:** 21 situações medidas pela CLI real antes de qualquer prompt (seção 2).
- **Mutação:** 18 mutantes feitos à mão, cada um uma substituição de texto no código do LST que
  simula uma falha de integração (seção 7). Um mutante é morto quando algum teste que passa no código
  original passa a falhar.
- **Subconjunto mínimo:** cobertura de conjuntos gulosa sobre os mutantes mortos e os defeitos
  revelados por cada suíte.

**Custo e tamanho de cada execução**

| Execução | Tokens consumidos | Tempo da sessão | Linhas de teste | Funções / casos |
|---|---|---|---|---|
| P0 | 198.630 | 18 min | 555 (4 arquivos) | 14 / 21 |
| P1 v1 | 154.128 | 31 min | 1.000 | 40 / 149 |
| P2 v1 | 143.576 | 28 min | 639 | 24 / 77 |
| P1 v2 | 189.826 | 37 min | 581 | 25 / 52 |
| P2 v2 | 163.400 | 33 min | 604 | 21 / 48 |

**Cobertura do módulo de integração** (`lst/explainer/*` + `lst/pipeline.py`, 173 comandos, 26 decisões)

| Suíte | Comandos | Decisões |
|---|---|---|
| P0 | 39% | 0% |
| P1 v1 | 98% | 100% |
| P2 v1 | 98% | 96% |
| P1 v2 | 97% | 92% |
| P2 v2 | 97% | 92% |
| Suíte do projeto (239 testes) | 98% | 96% |

## 2. Gabarito — comportamento real medido antes dos prompts

Executado pela CLI (`lst scan` sobre a fixture com 3 eventos marcados), com o servidor simulado e
`LLM_MAX_RETRIES=2`.

| Situação simulada no servidor | Comportamento real do LST |
|---|---|
| 200 válido em todas as chamadas | código 0; 3 requisições (uma por evento) |
| `LLM_TIMEOUT_SECONDS=5` | o timeout enviado ao cliente HTTP é 60 s (**D1**) |
| 429 sempre | código 1; 3 requisições (o SDK repete); "Erro inesperado: Error code: 429 …" |
| 500 sempre | código 1; 3 requisições; "Erro inesperado: Error code: 500 …" |
| 401 | código 1; 1 requisição; "Erro de autenticação no provedor LLM: …" |
| 404 (modelo ou URL errados) | código 1; 1 requisição; "Erro inesperado: Error code: 404 …" |
| 400 recusando `json_schema` (modo auto) | código 0; 6 requisições — a cascata recomeça a cada evento |
| 400 por outro motivo | código 1; 1 requisição; "Erro inesperado: Error code: 400 …" |
| 200 com `choices: []` | código 1; "Erro inesperado: list index out of range" (**D2**) |
| 200 com `content: null` | código 0; 6 requisições; eventos em "Eventos não explicados" |
| 200 com texto não-JSON | código 0; 6 requisições; "Eventos não explicados" |
| 200 com `severity` fora da lista | código 0; 6 requisições; "Eventos não explicados" |
| 200 com JSON entre cercas markdown | código 0; 3 requisições; eventos explicados |
| 200 com página HTML (URL errada) | código 1; "Erro inesperado: 'str' object has no attribute 'choices'" (**D2**) |
| Erro de conexão | código 1; 3 requisições; "Erro inesperado: Connection error." |
| Timeout de leitura | código 1; 3 requisições; "Timeout ao consultar o LLM: Request timed out." |
| 503 e depois 200 | código 0; 4 requisições |
| `LLM_PARSE_RETRIES=0` + não-JSON | código 0; 3 requisições; "Eventos não explicados" |
| `LLM_MAX_RETRIES=0` + 500 | código 1; 1 requisição |
| Evento 2 inválido duas vezes, demais válidos | código 0; 4 requisições; 1 evento em "Eventos não explicados" |
| Formato da requisição | `Authorization: Bearer <chave>`; corpo com `model`, `messages` [system, user], `max_tokens` 1024 e `response_format` json_schema; a chave não vai no corpo |
| `LLM_TIMEOUT_SECONDS=999`, `0.5`, `LLM_MAX_RETRIES=9` ou `LLM_STRUCTURED_MODE=xml` (chave presente) | código 1; "Erro: LLM_API_KEY não configurada no .env (ou use --dry-run)." (**D3**) |

## 3. Contrato usado nos prompts

```text
CONTRATO DA INTEGRAÇÃO LST → PROVEDOR DE LLM (API REST compatível com OpenAI)

Sistema sob teste
O LST (Log Sec Triage) é uma CLI em Python 3.11 que lê um arquivo de log, detecta eventos suspeitos de forma determinística e pede a um LLM, por uma API REST compatível com OpenAI, uma explicação em pt-BR para cada evento marcado. Nesta integração o LST é o cliente e o provedor de LLM (Ollama Cloud, OpenRouter, OpenAI...) é o servidor. Os testes não podem acessar a rede: o servidor deve ser simulado.

Pontos de entrada
- CLI: `lst scan <arquivo_log>`. Em teste: `typer.testing.CliRunner().invoke(lst.cli.app, ["scan", str(caminho)])`. A configuração vem de variáveis de ambiente ou de um arquivo `.env` no diretório atual.
- Python: `await lst.pipeline.run_pipeline(log_path: pathlib.Path, settings: lst.config.Settings) -> str` devolve o relatório em Markdown e propaga as exceções.
- `lst.config.Settings(_env_file=None, llm_api_key=..., ...)`: `_env_file=None` ignora o `.env` local; os demais campos têm os nomes das variáveis abaixo em minúsculas.

Configuração (variável | padrão | faixa | significado)
- LLM_API_KEY | — | obrigatória | enviada no cabeçalho `Authorization: Bearer <chave>`
- LLM_MODEL | gpt-oss:20b | — | campo `model` da requisição
- LLM_BASE_URL | https://ollama.com/v1 | — | o endpoint é `{LLM_BASE_URL}/chat/completions`
- LLM_TIMEOUT_SECONDS | 60.0 | [1.0, 300.0] | timeout de uma única chamada ao LLM
- LLM_MAX_RETRIES | 2 | [0, 5] | novas tentativas automáticas para falhas HTTP transitórias (5xx, rate-limit)
- LLM_PARSE_RETRIES | 1 | [0, 3] | novas requisições quando o provedor devolve 200 OK com resposta vazia ou inválida
- LLM_MAX_TOKENS | 1024 | [64, 4096] | campo `max_tokens` da requisição
- LLM_STRUCTURED_MODE | auto | auto, json_schema, json_object, none | estratégia de saída estruturada

Requisição enviada pelo LST
- Uma chamada `POST {LLM_BASE_URL}/chat/completions` por evento marcado, em sequência.
- Corpo JSON: `model`, `messages` = [mensagem `system`, mensagem `user`], `max_tokens` e, conforme o modo, `response_format`:
  - json_schema: `{"type": "json_schema", "json_schema": {"name": "triage_explanation", "strict": true, "schema": {...}}}`, com os três campos obrigatórios;
  - json_object: `{"type": "json_object"}`;
  - none: sem `response_format`.
- Modo auto: tenta json_schema; se o servidor responder 400 por causa de `response_format`, tenta json_object; se de novo, tenta sem `response_format`. Um 400 por outro motivo não degrada. Com o modo fixado, não há degradação: o 400 vira erro.
- Dados que saem da máquina: o template do evento e amostras de no máximo 3 IPs, 3 usuários e 3 linhas originais. A chave da API nunca vai no corpo.

Resposta esperada do servidor (200 OK)
- Corpo no formato chat.completion; `choices[0].message.content` traz um JSON com exatamente `explanation` (texto), `severity` (low | medium | high | critical) e `next_action` (texto). O LST tolera cercas markdown e texto antes ou depois do JSON e normaliza `severity` para minúsculas.
- 200 OK com resposta vazia, não-JSON, sem um dos três campos ou com `severity` fora da lista: o LST refaz a requisição até LLM_PARSE_RETRIES vezes; se continuar inválida, o evento é listado na seção "## Eventos não explicados" do relatório (nunca é descartado em silêncio) e o relatório é gerado normalmente.

Saídas observáveis da CLI
- Código 0: relatório gerado no stdout, inclusive quando há eventos não explicados. O relatório começa com "# Relatório de Triagem de Logs"; cada evento explicado tem as seções "### Explicação" e "### Próxima ação".
- Código 1: erro operacional (autenticação, timeout, validação de configuração), com mensagem em pt-BR no stderr e sem traceback. Mensagens documentadas: chave ausente → "Erro: LLM_API_KEY não configurada no .env (ou use --dry-run)."; chave inválida ou expirada → "Erro de autenticação no provedor LLM: ..."; o modelo demorou mais que LLM_TIMEOUT_SECONDS → "Timeout ao consultar o LLM: ...".
- Código 2: erro de uso; arquivo de log inexistente → "Erro: arquivo não encontrado: ...".
- `lst scan --dry-run`: não chama o provedor (zero requisições) e dispensa a chave.

Dados de teste disponíveis
- `tests/fixtures/auth_sample.log` (caminho relativo à raiz do repositório): log calibrado que produz exatamente 3 eventos marcados.
```

## 4. Prompts

Para não repetir, `{CONTRATO}` indica o texto da seção 3 e `{EXEMPLO}`, o teste-exemplo do
few-shot (arquivo `prompts/exemplo_fewshot.py`, conferido contra o código real antes do uso).

### P0 — zero-shot puro (linha de base)

```text
Crie testes de integração em pytest para o LST (Log Sec Triage), uma ferramenta de linha de comando em Python que lê um arquivo de log, detecta eventos suspeitos e envia cada evento a um LLM por uma API REST compatível com OpenAI (POST /chat/completions) para obter uma explicação. Use respx para simular o servidor. Os testes devem verificar a comunicação entre o LST e a API, incluindo respostas de sucesso e de erro (como 401, 429, 500 e timeout).
```

### P1 v1 — cenários de integração e dados de teste (zero-shot estruturado)

```text
Você é um engenheiro de testes experiente, especializado em testes funcionais, testes de API REST e testes de integração.

Crie um conjunto de testes de integração caixa-preta em pytest (Python 3.11), usando respx para simular o servidor HTTP, para a integração entre o LST e um provedor de LLM com API REST compatível com OpenAI. Use o contrato delimitado por ##### como especificação da integração. O conjunto deve cobrir a especificação e todas as respostas possíveis do servidor (códigos de status e formatos de corpo). Use Particionamento de Equivalência e Análise de Valor-Limite como critérios de teste. A resposta deve conter apenas código Python.

Se precisar de dados de teste, use o arquivo de log calibrado descrito no contrato e respostas do LLM em pt-BR com valores fictícios.

Siga estas cinco instruções para o código gerado:
1. Um único arquivo `tests/test_llm_integration.py`, com todos os imports necessários.
2. Nenhum acesso à rede: toda chamada ao provedor é simulada com respx.
3. Crie as fixtures e funções auxiliares necessárias (configuração isolada, respostas simuladas).
4. Isole o ambiente de cada teste (variáveis de ambiente e diretório atual) para que um `.env` local não interfira.
5. Cada teste com uma docstring de uma linha descrevendo o cenário de integração.

#####
{CONTRATO}
#####
```

### P2 v1 — casos de erro (cadeia de raciocínio + few-shot)

```text
Você é um engenheiro de testes experiente, especializado em testes de integração e em injeção de falhas na comunicação entre componentes.

Crie testes de integração em pytest para os casos de ERRO da integração entre o LST e um provedor de LLM com API REST compatível com OpenAI, descrita no contrato delimitado por #####. Pense passo a passo sobre todas as falhas que podem ocorrer na comunicação, incluindo falhas de rede, respostas HTTP de erro e respostas com conteúdo inválido. Para cada caso de erro, indique qual regra do contrato está sendo verificada. Siga o padrão do exemplo.

Vamos pensar passo a passo:
1. Identifique os pontos de comunicação entre os componentes envolvidos (CLI, configuração, pipeline, cliente HTTP, servidor, interpretação da resposta, relatório).
2. Para cada ponto, liste as falhas possíveis.
3. Para cada falha, determine o comportamento esperado segundo o contrato.
4. Considere casos de borda, como valores-limite de configuração e respostas vazias.
5. Escreva um teste pytest para cada falha, seguindo o padrão do exemplo, e indique na docstring a regra do contrato verificada.

Primeiro mostre, de forma resumida, o raciocínio dos passos 1 a 4; depois, o código completo em um único bloco, no arquivo `tests/test_llm_integration_errors.py`.

Exemplo de teste no padrão do projeto:
---
{EXEMPLO}
---

#####
{CONTRATO}
#####
```

### Interação de correção (sessão do P1 v1, no estilo da Figura 30)

```text
Os testes abaixo falharam ao executar. Informo o teste e a causa do erro. Sua tarefa é corrigir esses erros. Responda apenas com o código dos testes alterados (funções e listas de parâmetros afetadas), sem reescrever o arquivo inteiro. Continue sem usar ferramentas.

tests/test_llm_integration.py::test_timeout_configurado_vale_para_cada_chamada[limite-inferior]
    assert 60.0 == 1.0 ± 1.0e-06
tests/test_llm_integration.py::test_timeout_configurado_vale_para_cada_chamada[limite-superior]
    assert 60.0 == 300.0 ± 3.0e-04
tests/test_llm_integration.py::test_corpo_200_fora_do_formato_chat_completion_vira_evento_nao_explicado[choices-vazio]
    src/lst/explainer/client.py:210: IndexError: list index out of range
tests/test_llm_integration.py::test_corpo_200_fora_do_formato_chat_completion_vira_evento_nao_explicado[objeto-vazio]
    src/lst/explainer/client.py:210: TypeError: 'NoneType' object is not subscriptable
tests/test_llm_integration.py::test_corpo_200_fora_do_formato_chat_completion_vira_evento_nao_explicado[corpo-vazio]
    /usr/lib/python3.11/json/decoder.py:355: json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
tests/test_llm_integration.py::test_corpo_200_fora_do_formato_chat_completion_vira_evento_nao_explicado[html]
    src/lst/explainer/client.py:210: AttributeError: 'str' object has no attribute 'choices'
tests/test_llm_integration.py::test_corpo_200_fora_do_formato_chat_completion_vira_evento_nao_explicado[erro-dentro-de-200]
    src/lst/explainer/client.py:210: TypeError: 'NoneType' object is not subscriptable

Resultado da execução: 7 failed, 142 passed.
```

### P1 v2 — cenários ajustado

```text
Você é um engenheiro de testes experiente, especializado em testes funcionais, testes de API REST e testes de integração.

Crie um conjunto de testes de integração caixa-preta em pytest (Python 3.11), usando respx para simular o servidor HTTP, para a integração entre o LST e um provedor de LLM com API REST compatível com OpenAI. Use o contrato delimitado por ##### como especificação da integração. O conjunto deve cobrir a especificação e todas as respostas possíveis do servidor (códigos de status e formatos de corpo).

Critérios de teste:
- Particionamento de Equivalência: um único caso representativo por classe de equivalência. Prefira poucos casos fortes: o objetivo é cobrir todas as classes, não multiplicar exemplos da mesma classe.
- Análise de Valor-Limite: parametrize apenas os limites (mínimo, máximo e o primeiro valor fora da faixa).
- Valor aceito não é valor aplicado: para cada configuração, verifique que o valor aparece na requisição ou no comportamento observável, e não apenas que é aceito.
- Requisito de qualidade da equipe, além do contrato: toda mensagem de erro da CLI deve nomear a causa (a variável de configuração, o status HTTP ou o arquivo envolvido) e nunca expor ao analista uma exceção interna do Python.
- Lacunas: quando o contrato não definir um comportamento, não escreva asserção sobre ele; registre-o na lista de lacunas.

Se precisar de dados de teste, use o arquivo de log calibrado descrito no contrato e respostas do LLM em pt-BR com valores fictícios.

Siga estas cinco instruções para o código gerado:
1. Um único arquivo `tests/test_llm_integration.py`, com todos os imports necessários.
2. Nenhum acesso à rede: toda chamada ao provedor é simulada com respx.
3. Crie as fixtures e funções auxiliares necessárias (configuração isolada, respostas simuladas).
4. Isole o ambiente de cada teste (variáveis de ambiente e diretório atual) para que um `.env` local não interfira.
5. Cada teste com uma docstring de uma linha que começa pelo ID da partição, por exemplo "[P07] ...".

Formato da resposta, nesta ordem:
1. Tabela de partições: ID, classe (entrada ou estímulo do servidor), caso escolhido e resultado esperado segundo o contrato.
2. O código completo em um único bloco.
3. Lacunas do contrato: para cada comportamento não especificado, a pergunta a fazer ao responsável.

#####
{CONTRATO}
#####
```

### P2 v2 — erros ajustado

```text
Você é um engenheiro de testes experiente, especializado em testes de integração e em injeção de falhas na comunicação entre componentes.

Crie testes de integração em pytest para os casos de ERRO da integração entre o LST e um provedor de LLM com API REST compatível com OpenAI, descrita no contrato delimitado por #####. Pense passo a passo sobre todas as falhas que podem ocorrer na comunicação, incluindo falhas de rede, respostas HTTP de erro e respostas com conteúdo inválido. Para cada caso de erro, indique qual regra do contrato está sendo verificada. Siga o padrão do exemplo.

Vamos pensar passo a passo:
1. Identifique os pontos de comunicação entre os componentes envolvidos (CLI, configuração, pipeline, cliente HTTP, servidor, interpretação da resposta, relatório).
2. Para cada ponto, liste (a) as falhas possíveis e (b) os valores que precisam atravessá-lo: a configuração que deve chegar à requisição, os dados que não podem sair da máquina e os campos da resposta que devem chegar ao relatório. Um valor aceito na configuração mas não aplicado também é uma falha.
3. Para cada item, determine o comportamento esperado segundo o contrato. Se o contrato não o definir, registre-o como lacuna e não escreva asserção sobre ele.
4. Considere casos de borda: valores-limite de configuração (mínimo, máximo e o primeiro valor fora da faixa) e respostas vazias.
5. Nas saídas de erro, aplique também o requisito de qualidade da equipe, que vai além do contrato: a mensagem deve nomear a causa (a variável de configuração, o status HTTP ou o arquivo envolvido) e nunca expor ao analista uma exceção interna do Python.
6. Escreva um teste pytest por item, com um caso representativo por classe, seguindo o padrão do exemplo, e indique na docstring o ponto e a regra verificados.

Formato da resposta: primeiro, de forma resumida, o raciocínio dos passos 1 a 5; depois, o código completo em um único bloco, no arquivo `tests/test_llm_integration_errors.py`; por fim, as lacunas do contrato, cada uma com a pergunta a fazer ao responsável.

Exemplo de teste no padrão do projeto:
---
{EXEMPLO}
---

#####
{CONTRATO}
#####
```

## 5. Registro dos casos de teste gerados

Uma linha por função de teste gerada, com o cenário descrito pelo próprio modelo (docstring),
o número de casos (contando as parametrizações) e o resultado contra o código real. D1, D2 e D3 são
os defeitos da resposta; Q é o requisito de qualidade da equipe (mensagem que nomeia a causa),
introduzido na v2. O P0 não escreveu docstrings: o cenário é o nome da função.

### P0 — 14 funções de teste, 21 casos, 0 passam

| # | Teste gerado | Cenário (docstring do modelo) | Casos | Resultado |
|---|---|---|---|---|
| 1 | `test_401_aborta_sem_retentar` | (401 aborta sem retentar) | 1 | 1 falha (interface inventada) |
| 2 | `test_429_retenta_respeitando_retry_after` | (429 retenta respeitando retry after) | 1 | 1 falha (interface inventada) |
| 3 | `test_429_persistente_esgota_retentativas_e_aborta` | (429 persistente esgota retentativas e aborta) | 1 | 1 falha (interface inventada) |
| 4 | `test_5xx_transitorio_e_retentado_com_backoff` | (5xx transitorio e retentado com backoff) | 3 | 3 falham (interface inventada) |
| 5 | `test_5xx_persistente_esgota_retentativas_e_aborta` | (5xx persistente esgota retentativas e aborta) | 3 | 3 falham (interface inventada) |
| 6 | `test_timeout_transitorio_e_retentado` | (timeout transitorio e retentado) | 2 | 2 falham (interface inventada) |
| 7 | `test_timeout_persistente_esgota_retentativas_e_aborta` | (timeout persistente esgota retentativas e aborta) | 2 | 2 falham (interface inventada) |
| 8 | `test_200_invalido_falha_de_forma_controlada` | (200 invalido falha de forma controlada) | 2 | 2 falham (interface inventada) |
| 9 | `test_envia_uma_requisicao_por_evento_suspeito` | (envia uma requisicao por evento suspeito) | 1 | 1 falha (interface inventada) |
| 10 | `test_requisicao_segue_o_contrato_de_chat_completions` | (requisicao segue o contrato de chat completions) | 1 | 1 falha (interface inventada) |
| 11 | `test_timeout_configurado_chega_ao_cliente_http` | (timeout configurado chega ao cliente http) | 1 | 1 falha (interface inventada) |
| 12 | `test_explicacao_de_cada_evento_chega_a_saida` | (explicacao de cada evento chega a saida) | 1 | 1 falha (interface inventada) |
| 13 | `test_linhas_benignas_nao_saem_para_o_provedor` | (linhas benignas nao saem para o provedor) | 1 | 1 falha (interface inventada) |
| 14 | `test_log_sem_eventos_suspeitos_nao_chama_a_api` | (log sem eventos suspeitos nao chama a api) | 1 | 1 falha (interface inventada) |

### P1 v1 — 40 funções de teste, 149 casos, 142 passam

| # | Teste gerado | Cenário (docstring do modelo) | Casos | Resultado |
|---|---|---|---|---|
| 1 | `test_um_post_por_evento_com_bearer_modelo_mensagens_e_max_tokens` | Cada evento marcado gera um POST em /chat/completions com Bearer, modelo padrão, system+user e max_tokens padrão. | 1 | 1 passa |
| 2 | `test_chave_da_api_nunca_vai_no_corpo_nem_na_url` | A chave da API trafega só no cabeçalho Authorization, nunca no corpo JSON nem na URL. | 1 | 1 passa |
| 3 | `test_somente_template_e_amostras_limitadas_saem_da_maquina` | Cada requisição leva no máximo 3 linhas originais do log e no máximo 3 IPs de amostra fora delas. | 1 | 1 passa |
| 4 | `test_modelo_configurado_vai_no_campo_model` | O valor de LLM_MODEL é enviado no campo model de todas as requisições. | 2 | 2 passam |
| 5 | `test_max_tokens_nos_limites_vai_no_corpo` | LLM_MAX_TOKENS (padrão e limites da faixa) é enviado como max_tokens. | 3 | 3 passam |
| 6 | `test_timeout_configurado_vale_para_cada_chamada` | LLM_TIMEOUT_SECONDS é aplicado como timeout de leitura de cada chamada HTTP ao provedor. | 3 | 1 passa; 2 falham (D1) |
| 7 | `test_base_url_padrao_aponta_para_ollama_cloud` | Sem LLM_BASE_URL, o LST chama https://ollama.com/v1/chat/completions. | 1 | 1 passa |
| 8 | `test_base_url_personalizada_com_caminho` | Com LLM_BASE_URL de outro provedor, o endpoint chamado é {LLM_BASE_URL}/chat/completions. | 1 | 1 passa |
| 9 | `test_response_format_enviado_conforme_modo` | O response_format enviado segue LLM_STRUCTURED_MODE quando o provedor aceita a primeira tentativa. | 5 | 5 passam |
| 10 | `test_json_schema_declara_triage_explanation_estrito_com_tres_campos` | No modo json_schema o response_format declara triage_explanation, strict=true e os três campos obrigatórios. | 1 | 1 passa |
| 11 | `test_severidades_validas_sao_aceitas_sem_nova_requisicao` | Cada severity da lista, inclusive com maiúsculas (normalizada pelo LST), é aceita na primeira resposta. | 8 | 8 passam |
| 12 | `test_conteudo_valido_em_formatos_tolerados_entra_no_relatorio` | JSON válido com cerca markdown ou texto antes/depois é aceito e a explicação em pt-BR entra no relatório. | 7 | 7 passam |
| 13 | `test_conteudo_invalido_em_200_vira_evento_nao_explicado` | Conteúdo 200 vazio, não-JSON, sem campo obrigatório ou com severity inválida é listado como não explicado. | 14 | 14 passam |
| 14 | `test_corpo_200_fora_do_formato_chat_completion_vira_evento_nao_explicado` | Corpo 200 sem choices, vazio, HTML ou com erro embutido não derruba a triagem e o evento é listado. | 6 | 1 passa; 5 falham (D2) |
| 15 | `test_resposta_invalida_persistente_esgota_parse_retries` | 200 inválido persistente gera 1 + LLM_PARSE_RETRIES requisições por evento e o relatório sai normalmente. | 3 | 3 passam |
| 16 | `test_resposta_invalida_recupera_na_ultima_nova_requisicao` | Exatamente LLM_PARSE_RETRIES respostas 200 vazias seguidas de uma válida: o evento é explicado. | 2 | 2 passam |
| 17 | `test_resposta_invalida_uma_vez_alem_do_limite_isola_so_o_evento_afetado` | LLM_PARSE_RETRIES + 1 respostas inválidas no 1º evento: só ele fica não explicado e os demais são explicados. | 3 | 3 passam |
| 18 | `test_modo_auto_degrada_de_json_schema_para_json_object` | Modo auto: 400 por response_format em json_schema leva a nova tentativa com json_object e o evento é explicado. | 3 | 3 passam |
| 19 | `test_modo_auto_degrada_ate_requisicao_sem_response_format` | Modo auto: 400 por response_format em json_schema e em json_object leva a uma requisição sem response_format. | 1 | 1 passa |
| 20 | `test_modo_auto_400_apos_degradacao_completa_propaga_erro` | Modo auto: se a requisição já sem response_format também recebe 400, o erro é propagado após 3 chamadas. | 1 | 1 passa |
| 21 | `test_modo_fixado_nao_degrada_400_de_response_format` | Com LLM_STRUCTURED_MODE fixado, 400 por response_format vira erro sem tentar outro formato. | 2 | 2 passam |
| 22 | `test_falhas_transitorias_sao_repetidas_ate_o_sucesso` | 429 e 5xx (corpo JSON, HTML, texto ou vazio) são repetidos automaticamente com o mesmo corpo e o evento é explicado. | 6 | 6 passam |
| 23 | `test_falhas_transitorias_alem_do_limite_padrao_propagam_erro` | Com o padrão LLM_MAX_RETRIES=2, falha transitória persistente encerra com erro após exatamente 3 chamadas. | 6 | 6 passam |
| 24 | `test_503_persistente_faz_exatamente_1_mais_max_retries_chamadas` | 503 persistente: o LST faz 1 + LLM_MAX_RETRIES chamadas (limites 0 e 5) e então propaga o erro. | 4 | 4 passam |
| 25 | `test_503_recupera_na_ultima_tentativa_permitida` | Exatamente LLM_MAX_RETRIES respostas 503 seguidas de 200 válido: o evento é explicado normalmente. | 3 | 3 passam |
| 26 | `test_erros_4xx_nao_sao_repetidos_nem_degradam` | 4xx não transitórios (400 por outro motivo, 401, 403, 404, 422) são propagados após uma única chamada. | 10 | 10 passam |
| 27 | `test_pipeline_propaga_timeout_do_provedor` | Um timeout de leitura na chamada ao LLM é propagado por run_pipeline como exceção. | 1 | 1 passa |
| 28 | `test_settings_aceita_limites_da_faixa_vindos_do_ambiente` | Valores nos limites das faixas, lidos de variáveis de ambiente, são aceitos sem alteração. | 12 | 12 passam |
| 29 | `test_settings_rejeita_valores_fora_da_faixa` | Valores logo fora das faixas documentadas ou de tipo inválido são rejeitados na validação. | 10 | 10 passam |
| 30 | `test_settings_com_env_file_none_ignora_dotenv_local` | Settings(_env_file=None) ignora um .env no diretório atual e envia os valores padrão ao provedor. | 1 | 1 passa |
| 31 | `test_cli_gera_relatorio_markdown_no_stdout` | Com o provedor respondendo 200 válido, a CLI sai com 0 e imprime o relatório com os 3 eventos explicados. | 1 | 1 passa |
| 32 | `test_cli_sai_com_0_mesmo_com_eventos_nao_explicados` | Respostas 200 inválidas persistentes não derrubam a CLI: código 0 e seção de eventos não explicados. | 1 | 1 passa |
| 33 | `test_cli_aceita_configuracao_nos_limites_e_reflete_na_requisicao` | A CLI aceita todas as variáveis nos limites da faixa e as reflete nas requisições ao provedor. | 2 | 2 passam |
| 34 | `test_cli_configuracao_invalida_sai_com_1_sem_chamar_provedor` | Configuração fora da faixa faz a CLI sair com código 1, mensagem no stderr, sem traceback e sem requisições. | 10 | 10 passam |
| 35 | `test_cli_sem_chave_sai_com_1_sem_chamar_provedor` | Sem LLM_API_KEY (ausente ou vazia) a CLI sai com código 1, mensagem no stderr e zero requisições. | 2 | 2 passam |
| 36 | `test_cli_chave_invalida_ou_expirada_sai_com_erro_de_autenticacao` | HTTP 401 do provedor, em qualquer formato de corpo, vira código 1 com erro de autenticação e sem novas tentativas. | 6 | 6 passam |
| 37 | `test_cli_timeout_do_modelo_sai_com_1` | Quando o modelo excede LLM_TIMEOUT_SECONDS, a CLI sai com código 1 e 'Timeout ao consultar o LLM'. | 1 | 1 passa |
| 38 | `test_cli_arquivo_de_log_inexistente_sai_com_2` | Arquivo de log inexistente gera código 2, a mensagem documentada e nenhuma requisição ao provedor. | 1 | 1 passa |
| 39 | `test_cli_dry_run_nao_chama_provedor_e_dispensa_chave` | lst scan --dry-run termina com código 0 sem nenhuma requisição ao provedor, com ou sem LLM_API_KEY. | 2 | 2 passam |
| 40 | `test_cli_le_configuracao_do_dotenv_do_diretorio_atual` | Sem variáveis de ambiente, a CLI usa a chave, a URL e o modelo definidos no .env do diretório atual. | 1 | 1 passa |

### P2 v1 — 24 funções de teste, 77 casos, 74 passam

| # | Teste gerado | Cenário (docstring do modelo) | Casos | Resultado |
|---|---|---|---|---|
| 1 | `test_settings_reject_values_outside_documented_range` | Regra: faixas da configuração — valor fora de [mín, máx] ou fora do domínio é rejeitado. | 9 | 9 passam |
| 2 | `test_settings_accept_closed_range_limits` | Regra: as faixas são fechadas — os próprios limites são aceitos (controle de borda). | 12 | 12 passam |
| 3 | `test_cli_invalid_config_is_operational_error` | Regra: erro de validação de configuração — código 1, mensagem pt-BR no stderr, sem traceback e sem nenhuma requisição ao provedor. | 7 | 7 passam |
| 4 | `test_cli_validates_config_read_from_dotenv` | Regra: a configuração também vem do `.env` do diretório atual e passa pela mesma validação. | 1 | 1 passa |
| 5 | `test_cli_without_api_key_fails_before_any_request` | Regra: LLM_API_KEY é obrigatória — código 1, mensagem documentada e zero requisições (chave vazia é tratada como ausente: um `Bearer ` vazio não pode sair da máquina). | 2 | 2 passam |
| 6 | `test_cli_dry_run_skips_provider_and_key` | Regra: `--dry-run` dispensa a chave e faz zero requisições (saída sugerida pelo erro de chave). | 1 | 1 passa |
| 7 | `test_cli_missing_log_file_is_usage_error` | Regra: arquivo de log inexistente — código 2, "Erro: arquivo não encontrado: ...", sem LLM. | 1 | 1 passa |
| 8 | `test_cli_invalid_api_key_is_auth_error_without_retry` | Regra: chave inválida/expirada (401) — código 1, "Erro de autenticação no provedor LLM: ..."; 401 não é falha transitória: nenhuma nova tentativa, mesmo com LLM_MAX_RETRIES=5. | 1 | 1 passa |
| 9 | `test_cli_key_revoked_mid_scan_stops_at_failing_event` | Regra: os eventos são consultados em sequência; um 401 no 2º evento encerra a varredura com código 1 e o 3º evento não é consultado. | 1 | 1 passa |
| 10 | `test_cli_llm_timeout_exits_1_with_documented_message` | Regra: o modelo demorou mais que LLM_TIMEOUT_SECONDS (aqui no limite inferior, 1.0) — código 1, "Timeout ao consultar o LLM: ...", sem traceback. | 1 | 1 passa |
| 11 | `test_cli_network_failure_is_operational_error` | Regra: falha de rede é erro operacional — código 1, mensagem no stderr e sem traceback (o texto não é documentado; verifica-se a saída controlada). | 2 | 2 passam |
| 12 | `test_transient_http_failure_is_retried_and_event_recovered` | Regra: LLM_MAX_RETRIES cobre falhas transitórias (5xx, rate-limit); a nova tentativa bem sucedida gera o relatório completo, sem rodapé, com a chave só no cabeçalho Authorization. | 5 | 5 passam |
| 13 | `test_persistent_transient_failure_stops_after_max_retries` | Regra: no máximo LLM_MAX_RETRIES novas tentativas (faixa [0, 5]); esgotadas, run_pipeline propaga a exceção — falha HTTP não vira "evento não explicado" (isso é só para 200 inválido). | 6 | 6 passam |
| 14 | `test_non_transient_http_error_is_not_retried` | Regra: só 5xx e rate-limit são transitórios — os demais 4xx não geram nova tentativa e, no modo auto, um 400 por motivo alheio a `response_format` não degrada. A exceção é propagada. | 5 | 5 passam |
| 15 | `test_auto_mode_degrades_on_response_format_400` | Regra: modo auto — tenta json_schema; 400 por `response_format` → json_object; de novo → sem `response_format`. O schema exige os três campos e a chave nunca vai no corpo. | 2 | 2 passam |
| 16 | `test_auto_mode_fails_when_last_fallback_is_also_rejected` | Regra: o modo auto tem só três degraus; um 400 na requisição sem `response_format` é erro propagado — sem laço de novas tentativas, mesmo com LLM_MAX_RETRIES=5. | 1 | 1 passa |
| 17 | `test_fixed_structured_mode_turns_400_into_error` | Regra: com LLM_STRUCTURED_MODE fixado não há degradação — o 400 vira erro. | 3 | 3 passam |
| 18 | `test_invalid_200_reply_is_retried_then_listed_as_unexplained` | Regra: 200 OK vazio, não-JSON, sem um campo ou com severity fora da lista → até LLM_PARSE_RETRIES novas requisições (contador separado de LLM_MAX_RETRIES); se continuar inválido, o evento vai para "## Eventos não explicados" e o relatório é gerado normalmente. | 8 | 5 passam; 3 falham (D2) |
| 19 | `test_parse_retries_limits_are_respected` | Regra: LLM_PARSE_RETRIES ∈ [0, 3] — cada evento recebe exatamente 1 + N requisições. | 2 | 2 passam |
| 20 | `test_parse_retry_recovers_event_after_invalid_reply` | Regra: a nova requisição de LLM_PARSE_RETRIES pode recuperar o evento — relatório sem rodapé. | 1 | 1 passa |
| 21 | `test_only_the_invalid_event_goes_to_unexplained_section` | Regra: o evento inválido é listado em "## Eventos não explicados" sem afetar os demais. | 1 | 1 passa |
| 22 | `test_truncated_reply_at_minimum_max_tokens_becomes_unexplained` | Regra: LLM_MAX_TOKENS no limite inferior (64) vai no campo `max_tokens`; o JSON cortado (finish_reason=length) é resposta inválida → evento não explicado, sem exceção. | 1 | 1 passa |
| 23 | `test_tolerated_formats_do_not_trigger_parse_retries` | Regra (controle negativo): cercas markdown, texto ao redor e severity em maiúsculas são tolerados — não contam como resposta inválida, não geram nova requisição nem rodapé. | 3 | 3 passam |
| 24 | `test_cli_exits_0_and_prints_report_with_unexplained_events` | Regra: código 0 inclusive com eventos não explicados — relatório completo no stdout. | 1 | 1 passa |

### P1 v2 — 25 funções de teste, 52 casos, 39 passam

| # | Teste gerado | Cenário (docstring do modelo) | Casos | Resultado |
|---|---|---|---|---|
| 1 | `test_configuracao_padrao` | [P01] Só com LLM_API_KEY: os padrões vão na requisição e o relatório traz os 3 eventos explicados. | 1 | 1 passa |
| 2 | `test_configuracao_pelo_dotenv` | [P02] Chave, modelo e URL lidos do .env do diretório atual são aplicados na requisição. | 1 | 1 passa |
| 3 | `test_chave_ausente` | [P03] Sem LLM_API_KEY: código 1, mensagem documentada no stderr e nenhuma requisição. | 1 | 1 passa |
| 4 | `test_dry_run` | [P04] --dry-run não faz requisições e dispensa a chave. | 1 | 1 passa |
| 5 | `test_arquivo_inexistente` | [P05] Log inexistente: código 2 e mensagem que nomeia o arquivo, sem requisições. | 1 | 1 passa |
| 6 | `test_max_tokens_nos_limites` | [P06] LLM_MAX_TOKENS no mínimo e no máximo chega ao campo max_tokens. | 2 | 2 passam |
| 7 | `test_timeout_nos_limites` | [P07] LLM_TIMEOUT_SECONDS no mínimo e no máximo vira o timeout de cada chamada. | 2 | 2 falham (D1) |
| 8 | `test_max_retries_nos_limites` | [P08] Com 503 persistente, o evento recebe exatamente 1 + LLM_MAX_RETRIES tentativas. | 2 | 2 passam |
| 9 | `test_parse_retries_nos_limites` | [P09] Com 200 inválido persistente, cada evento recebe 1 + LLM_PARSE_RETRIES requisições e fica sem explicação. | 2 | 2 passam |
| 10 | `test_configuracao_invalida` | [P10–P12] Configuração inválida: código 1, mensagem que nomeia a variável e nenhuma requisição. | 10 | 10 falham (D3) |
| 11 | `test_modo_estruturado_fixado` | [P13–P15] LLM_STRUCTURED_MODE fixado define o response_format enviado (ou a ausência dele). | 3 | 3 passam |
| 12 | `test_dados_enviados_ao_provedor` | [P16] Corpo com mensagens system e user, no máximo 3 linhas originais do log e sem a chave da API. | 1 | 1 passa |
| 13 | `test_uma_chamada_por_evento_em_sequencia` | [P17] Uma requisição por evento marcado, em sequência: nunca há duas em andamento. | 1 | 1 passa |
| 14 | `test_run_pipeline_aplica_settings` | [P18] run_pipeline devolve o Markdown e aplica modelo, URL, max_tokens e modo vindos de Settings. | 1 | 1 passa |
| 15 | `test_run_pipeline_propaga_excecao` | [P19] run_pipeline propaga uma exceção (não encerra o processo) quando o provedor recusa a chave. | 1 | 1 passa |
| 16 | `test_variacoes_toleradas` | [P20–P21] JSON entre cercas e texto, ou severity em maiúsculas, é aceito sem nova requisição. | 2 | 2 passam |
| 17 | `test_conteudo_invalido_vai_para_nao_explicados` | [P22–P25] 200 inválido é pedido de novo (LLM_PARSE_RETRIES=1) e, persistindo, o evento vai para não explicados. | 4 | 4 passam |
| 18 | `test_conteudo_invalido_seguido_de_valido` | [P26] Após 200 inválido, a resposta válida da nova requisição é usada e o evento é explicado. | 1 | 1 passa |
| 19 | `test_auto_degrada_quando_response_format_nao_suportado` | [P27] Modo auto: 400 por response_format degrada json_schema → json_object → sem response_format. | 1 | 1 passa |
| 20 | `test_auto_nao_degrada_com_400_por_outro_motivo` | [P28] Modo auto: 400 sem relação com response_format não degrada nem é repetido. | 1 | 1 passa |
| 21 | `test_modo_fixado_nao_degrada` | [P29] Modo fixado: 400 por response_format não degrada e vira erro que nomeia o status. | 1 | 1 passa |
| 22 | `test_chave_recusada` | [P30] 401: código 1, mensagem de autenticação que nomeia a causa e nenhuma nova tentativa. | 1 | 1 passa |
| 23 | `test_falha_transitoria_seguida_de_sucesso` | [P31–P32] 429 ou 5xx isolado é repetido automaticamente com o mesmo corpo e o evento é explicado. | 2 | 2 passam |
| 24 | `test_timeout` | [P33] Sem resposta no prazo: código 1 e mensagem de timeout que nomeia LLM_TIMEOUT_SECONDS. | 1 | 1 falha (Q) |
| 25 | `test_respostas_nao_especificadas` | [P34–P41] Respostas fora do contrato: só o requisito da equipe (sem exceção interna; erro nomeia a causa). | 8 | 8 passam |

### P2 v2 — 21 funções de teste, 48 casos, 33 passam

| # | Teste gerado | Cenário (docstring do modelo) | Casos | Resultado |
|---|---|---|---|---|
| 1 | `test_missing_api_key_fails_before_any_request` | Ponto: configuração → CLI. Regra: LLM_API_KEY é obrigatória; ausente → código 1 com a mensagem documentada e nenhuma requisição. | 1 | 1 passa |
| 2 | `test_invalid_setting_is_rejected_naming_the_variable` | Ponto: configuração → CLI. Regra: faixas [1.0, 300.0], [0, 5], [0, 3], [64, 4096] e modos válidos; o primeiro valor fora (ou de tipo errado) → código 1 por validação, sem requisição. | 10 | 10 falham (D3) |
| 3 | `test_limit_values_are_accepted` | Ponto: configuração. Regra: as faixas são fechadas; mínimo e máximo são aceitos. A aplicação de cada limite é verificada nos testes de requisição, timeout e novas tentativas. | 8 | 8 passam |
| 4 | `test_missing_log_file_is_usage_error_naming_the_file` | Ponto: CLI → pipeline. Regra: arquivo de log inexistente → código 2, "Erro: arquivo não encontrado: ..." com o arquivo nomeado, e nada é enviado ao provedor. | 1 | 1 passa |
| 5 | `test_dry_run_sends_nothing_and_does_not_require_key` | Ponto: CLI → cliente HTTP. Regra: --dry-run não chama o provedor (zero requisições) e dispensa a chave. A saída e o código do dry-run não são definidos (lacuna). | 1 | 1 passa |
| 6 | `test_configuration_reaches_every_request` | Ponto: pipeline → requisição. Regra: endpoint {LLM_BASE_URL}/chat/completions, LLM_MODEL em `model`, LLM_MAX_TOKENS (limites) em `max_tokens`, mensagens [system, user], chave só no cabeçalho Bearer e nunca no corpo, uma chamada por evento. | 2 | 2 passam |
| 7 | `test_structured_mode_is_applied_to_every_request` | Ponto: pipeline → requisição. Regra: LLM_STRUCTURED_MODE define o `response_format`; no json_schema, name=triage_explanation, strict=true e os três campos obrigatórios. | 3 | 3 passam |
| 8 | `test_only_sampled_log_data_leaves_the_machine` | Ponto: pipeline → requisição. Regra: saem só o template e amostras de no máximo 3 IPs, 3 usuários e 3 linhas originais por evento. O log é o fixture com cada linha repetida para 10 IPs (203.0.113.0/24) e 10 usuários sintéticos, para que os eventos tenham mais de 3 de cada. | 1 | 1 passa |
| 9 | `test_timeout_seconds_is_applied_to_each_call` | Ponto: cliente HTTP ↔ servidor. Regra: LLM_TIMEOUT_SECONDS (limites 1.0 e 300.0) limita uma chamada; estouro → código 1 e "Timeout ao consultar o LLM: ...", nomeando a variável. | 2 | 2 falham (D1) |
| 10 | `test_network_failure_does_not_expose_internal_exception` | Ponto: cliente HTTP ↔ servidor (rede). Regra da equipe: nenhuma exceção interna exposta; havendo saída de erro, ela nomeia LLM_BASE_URL. Código e novas tentativas: lacunas. | 2 | 2 falham (Q) |
| 11 | `test_invalid_key_is_authentication_error_without_retry` | Ponto: servidor → CLI. Regra: chave inválida → código 1, "Erro de autenticação no provedor LLM: ..." com o status; 401 não é falha transitória, logo não há nova tentativa. | 1 | 1 passa |
| 12 | `test_server_error_is_retried_exactly_max_retries_times` | Ponto: cliente HTTP ↔ servidor. Regra: 5xx é transitório; LLM_MAX_RETRIES (limites 0 e 5) novas tentativas, nem mais nem menos. O desfecho após esgotá-las é lacuna. | 2 | 2 passam |
| 13 | `test_rate_limit_is_retried_and_event_is_explained` | Ponto: cliente HTTP ↔ servidor. Regra: 429 (rate-limit) é transitório; a nova tentativa bem-sucedida gera o relatório completo. | 1 | 1 passa |
| 14 | `test_non_transient_client_error_is_not_retried` | Ponto: servidor → CLI. Regra: só 5xx e rate-limit têm nova tentativa; um 404 (LLM_BASE_URL ou modelo errado) não. Regra da equipe: sem exceção interna; havendo erro, nomeia o status. | 1 | 1 passa |
| 15 | `test_auto_mode_degrades_when_response_format_is_rejected` | Ponto: servidor → cliente HTTP. Regra: no modo auto, 400 por `response_format` degrada json_schema → json_object → sem response_format, e o evento é explicado. | 1 | 1 passa |
| 16 | `test_auto_mode_does_not_degrade_on_unrelated_400` | Ponto: servidor → cliente HTTP. Regra: um 400 por outro motivo não degrada (nenhum json_object é tentado). O desfecho desse 400 é lacuna. | 1 | 1 passa |
| 17 | `test_fixed_mode_turns_response_format_400_into_error` | Ponto: servidor → CLI. Regra: com o modo fixado não há degradação e o 400 vira erro. Regra da equipe: a mensagem nomeia o status 400, sem exceção interna. | 1 | 1 passa |
| 18 | `test_invalid_reply_is_retried_then_listed_as_unexplained` | Ponto: resposta → interpretação → relatório. Regra: 200 OK vazio, não-JSON, sem campo ou com severity fora da lista → nova requisição (LLM_PARSE_RETRIES padrão = 1); persistindo, o evento vai para "## Eventos não explicados" e o relatório é gerado normalmente. | 5 | 4 passam; 1 falha (D2) |
| 19 | `test_parse_retries_limits_are_applied` | Ponto: resposta → interpretação. Regra: LLM_PARSE_RETRIES (limites 0 e 3) novas requisições por evento com resposta inválida, nem mais nem menos. | 2 | 2 passam |
| 20 | `test_report_keeps_recovered_and_unexplained_events` | Ponto: interpretação → relatório. Regra: a nova requisição válida recupera o evento; o evento que segue inválido é listado e não derruba o relatório dos demais. | 1 | 1 passa |
| 21 | `test_tolerated_reply_format_is_not_treated_as_invalid` | Ponto: resposta → interpretação → relatório. Regra: cercas markdown, texto em volta e severity em maiúsculas são tolerados (sem nova requisição); explanation e next_action chegam ao relatório. | 1 | 1 passa |

## 6. Resultado da interação de correção

A resposta do modelo (literal em `saidas/p1-v1-correcao.md`) manteve o oráculo dos cinco casos de
200 malformado e os marcou como falha esperada (`xfail` estrito, com o tipo de exceção
observado). Para o timeout, declarou o próprio oráculo um "detalhe de implementação", trocou-o por
um servidor lento simulado e marcou só o limite superior como defeito. Executada, a suíte corrigida
teve 143 casos aprovados, 6 falhas esperadas e 1 falha: o limite inferior do timeout, que o modelo
supôs funcionar. O tempo de execução passou de 6,5 s para 14,5 s, e a suíte continuou matando os 18
mutantes.

## 7. Mutantes

| Mutante | Falha de integração simulada | P1 v1 | P2 v1 | P1 v2 | P2 v2 | Projeto |
|---|---|---|---|---|---|---|
| M01 | cascata nunca degrada (todo 400 vira erro) | morto | morto | morto | morto | morto |
| M02 | cascata degrada em qualquer 400 | morto | morto | morto | morto | morto |
| M03 | modo auto pula json_object | morto | morto | morto | morto | morto |
| M04 | max_tokens não enviado no modo json_schema | morto | morto | morto | morto | **vivo** |
| M05 | LLM_MAX_RETRIES ignorado (sem novas tentativas) | morto | morto | morto | morto | **vivo** |
| M06 | LLM_BASE_URL ignorado | morto | morto | morto | morto | **vivo** |
| M07 | chave configurada não vai no Authorization | morto | morto | morto | morto | **vivo** |
| M08 | LLM_PARSE_RETRIES ignorado no motor | morto | morto | morto | morto | morto |
| M09 | evento inválido descartado em silêncio | morto | morto | morto | morto | morto |
| M10 | severidade fora da lista aceita (vira medium) | morto | morto | morto | morto | morto |
| M11 | pipeline não repassa LLM_PARSE_RETRIES | morto | morto | morto | morto | **vivo** |
| M12 | pipeline não repassa LLM_MODEL | morto | **vivo** | morto | morto | **vivo** |
| M13 | severidade não normalizada para minúsculas | morto | morto | morto | morto | morto |
| M14 | mais de 3 amostras saem da máquina | morto | **vivo** | **vivo** | morto | morto |
| M15 | CLI perde a mensagem de autenticação | morto | morto | morto | morto | **vivo** |
| M16 | timeout sai com código 2 | morto | morto | **vivo** | **vivo** | **vivo** |
| M17 | relatório omite 'Eventos não explicados' | morto | morto | morto | morto | morto |
| M18 | --dry-run passa a exigir a chave | morto | morto | morto | morto | morto |
| **Total** | | **18/18** | **16/18** | **16/18** | **17/18** | **10/18** |

Para comparação, os 6 testes de integração que o projeto já tinha (`tests/test_pipeline.py`, que
trocam o cliente HTTP por um falso) matam sozinhos 1 dos 18 mutantes: eles não passam pela
fronteira HTTP, que é onde estão quase todas as falhas simuladas.

O M16 sobreviveu às duas v2 porque os testes de timeout delas já falham no código original (D1 e
Q): um teste vermelho não detecta uma regressão nova no mesmo caminho. O M14 sobreviveu ao P1 v2
porque o modelo declarou não verificável, de fora, o limite de 3 IPs e 3 usuários (lacuna 15).

## 8. Lacunas do contrato levantadas pelas versões v2

### P1 v2

1. **`--dry-run`:** qual o código de saída e o que vai para o stdout? Gera relatório? Com quais seções?
2. **Tentativas esgotadas para 5xx/429:** o scan aborta com código 1 (com qual mensagem) ou o evento vai para "Eventos não explicados" e os demais continuam?
3. **400 em modo fixado ou por outro motivo:** qual o código de saída exato e o texto da mensagem? Sai um relatório parcial?
4. **Como reconhecer um "400 por causa de `response_format`":** pelo `error.param`, pelo texto da mensagem ou pelo `error.code`? E nos provedores que devolvem `{"error": "texto"}`, como o Ollama?
5. **Degradação no modo auto:** o formato degradado vale para os eventos seguintes ou cada evento recomeça em json_schema?
6. **403, 404, 3xx e demais 4xx (408, 409, 413, 422):** como são classificados (autenticação ou erro operacional)? Com que código de saída? São repetidos?
7. **Timeout e falha de conexão (DNS, conexão recusada, TLS):** contam como falha transitória para `LLM_MAX_RETRIES`? Qual código e qual mensagem para falha de conexão?
8. **Escopo do timeout:** vale por tentativa ou para a chamada inteira, com as novas tentativas? Cobre conexão e leitura? (P07 supõe que ele vira o timeout do cliente HTTP.)
9. **Espera entre tentativas:** existe backoff? O LST respeita `Retry-After`/`retry-after-ms`? Com que teto?
10. **200 com corpo fora do formato chat.completion** (HTML, `choices` vazio, `content: null`, objeto `error` com status 200, comum em agregadores): isso conta como "resposta inválida" (nova requisição e "não explicados") ou como erro operacional?
11. **JSON fora do esperado:** campos além dos três invalidam a resposta ("exatamente")? `explanation` ou `next_action` vazios são aceitos? Se houver vários objetos JSON no texto, qual vale? `finish_reason: "length"` muda algo?
12. **Severidade no relatório:** a severidade aparece? Em que formato? Espaços (" High ") são tolerados?
13. **Novas requisições de parse:** repetem o corpo ou acrescentam uma instrução corretiva? Um 5xx durante uma delas consome o orçamento de `LLM_MAX_RETRIES` ou o de `LLM_PARSE_RETRIES`?
14. **Seção "## Eventos não explicados":** como cada evento é identificado nela? Ela aparece quando está vazia? Qual a ordem dos eventos no relatório?
15. **Formato da mensagem `user` e escolha das amostras:** sem saber como as amostras são serializadas, não dá para verificar de fora o limite de 3 IPs e 3 usuários. P16 verifica só as linhas originais e a chave.
16. **Chave vazia:** `LLM_API_KEY` vazia ou só com espaços conta como ausente?
17. **Precedência:** se o ambiente e o `.env` definem a mesma variável, qual vale?
18. **Barra final no `LLM_BASE_URL`:** um valor como `…/v1/` é normalizado ou gera `//chat/completions`?
19. **Código 2:** a mensagem vai para o stderr? O código também vale para diretório no lugar de arquivo, arquivo sem permissão de leitura e log vazio? Um log sem eventos marcados gera relatório com código 0?
20. **Mascaramento da chave:** as mensagens de erro devem mascarar a chave, por exemplo quando o provedor devolve parte dela?
21. **Campos e cabeçalhos extras:** o corpo pode ter outros campos (`temperature`, `stream`, `seed`)? E cabeçalhos extras?
22. **Erro de validação de configuração:** qual o texto da mensagem? Ela lista todas as variáveis inválidas ou só a primeira?
23. **Exceções de `run_pipeline`:** que tipos ela propaga? Uma hierarquia própria do LST ou as exceções do SDK e do httpx?

### P2 v2

1. **Esgotamento das novas tentativas (5xx/429).** "Depois de `1 + LLM_MAX_RETRIES` falhas, o LST aborta com código 1 ou lista o evento em 'Eventos não explicados' e segue? Com qual mensagem?"
2. **Falhas de rede.** "Conexão recusada, DNS, TLS e conexão interrompida contam como transitórias para `LLM_MAX_RETRIES`? Com qual código de saída e mensagem?"
3. **Semântica do timeout.** "`LLM_TIMEOUT_SECONDS` é o limite total da chamada ou um limite por operação (connect/read do httpx)? Um timeout gera nova tentativa?"
4. **Espera entre tentativas.** "Há backoff? O `Retry-After` do 429/503 é respeitado, e com que teto?" (Isso define a duração da suíte com `LLM_MAX_RETRIES=5`.)
5. **Outros 4xx.** "Qual o desfecho de 403, 404, 413 e 422? Um 403 conta como 'erro de autenticação'?"
6. **400 que vira erro.** "No modo fixado, e no `auto` quando o 400 não é de `response_format`, qual o código de saída e a mensagem?"
7. **Detecção do 400 de `response_format`.** "O LST decide pelo `error.param`, pelo texto da mensagem ou por um código? O formato de erro de cada provedor (Ollama Cloud, OpenRouter, OpenAI) foi validado?"
8. **Memória da degradação.** "Depois de degradar no 1º evento, os eventos seguintes recomeçam em `json_schema` ou usam o modo que funcionou?"
9. **Exceções de `run_pipeline`.** "Que tipos ela propaga em cada erro operacional? Há uma hierarquia própria do LST?"
10. **Relatório parcial.** "Se um erro operacional ocorre no 2º evento, o relatório dos eventos já explicados vai para o stdout?"
11. **Formato de 'Eventos não explicados'.** "Como cada evento é identificado ali (template, ocorrências, motivo, tentativas)?" Sem essa definição, não é possível provar que os 3 eventos foram listados.
12. **`severity` no relatório.** "A severidade aparece no relatório? Em que seção e em que formato?"
13. **Envelope inválido com 200.** "`choices` vazio, `content` null, corpo HTML ou `finish_reason: "length"` contam como resposta inválida (nova requisição) ou como erro?"
14. **Campos extras.** "O contrato diz 'exatamente' três campos. Um JSON com um campo a mais é inválido ou tolerado?"
15. **Chave vazia e vazamento.** "`LLM_API_KEY` vazia ou só com espaços equivale a ausente? Mensagens de erro e logs podem conter a chave ou trechos do log?"
16. **Validação da configuração.** "Qual o texto da mensagem para valor fora da faixa ou de tipo inválido? A faixa de `LLM_TIMEOUT_SECONDS` tem precisão definida (0.99 é inválido)? `LLM_STRUCTURED_MODE` aceita maiúsculas?"
17. **Precedência.** "Se a variável existe no ambiente e no `.env`, qual vale?"
18. **Saída do `--dry-run`.** "O que o `--dry-run` imprime e com que código termina?"
19. **Amostras.** "Como as 3 amostras são escolhidas (as primeiras, as mais frequentes)? As linhas vão íntegras ou podem ser truncadas ou mascaradas? Hostnames e portas também têm limite?"

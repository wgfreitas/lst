# Interação com o LLM

O LLM é usado APENAS no 5º estágio do pipeline (Explainer); a detecção é 100% determinística (ver [detection_rules.md](detection_rules.md)). O modelo recebe um evento já classificado e devolve três strings: explicação em pt-BR, severidade e próxima ação. Este documento lista o que sai da infra local, o que volta e como o retorno é validado. Diagrama do pipeline em [architecture.md](architecture.md).

## 1. Quando o LLM é chamado

O Explainer recebe a lista de `FlaggedEvent` do Detector e faz **uma chamada sequencial por evento** contra o endpoint de chat-completions do provedor configurado (`LLM_BASE_URL`, default `https://ollama.com/v1`), compatível com OpenAI. No transporte, os únicos retries são os da lib `openai` via `max_retries`; há ainda um retry de parsing na aplicação (seção 6). Em `--dry-run`, o LLM não é chamado: o pipeline gera placeholders neutros para validar parsing e estrutura sem custo de token.

## 2. O system prompt

Literal de `src/lst/explainer/prompt.py`:

```text
Você é um analista sênior de SOC revisando eventos de segurança.
Para cada evento recebido, produza estritamente um JSON com os campos:
- "explanation": 1-2 frases explicando o que o evento indica
- "severity": exatamente um de ["low", "medium", "high", "critical"]
- "next_action": 1 frase com a próxima ação investigativa

Responda SOMENTE com o JSON, sem texto antes ou depois, sem markdown
fences, sem comentários. Todas as strings em português brasileiro.
```

Racional: pt-BR no system porque misturar idiomas vaza para a saída. JSON estrito porque o parser a jusante é literal. Quatro níveis (`low|medium|high|critical`) para casar com o enum `Severity` do schema e com convenções comuns de ticketing.

## 3. O user prompt

Construído dinamicamente a partir do `FlaggedEvent`, em Markdown compacto (300–500 tokens por evento). Campos incluídos: template canônico com placeholders `<*>`; categoria, nome da regra e score; contagem total; cardinalidade e amostra (até 3) de IPs e usuários únicos; taxa média e de pico por minuto; janela temporal em ISO-8601; `context_notes` do Detector; até 3 linhas originais numeradas.

Exemplo com dados sintéticos (campos condensados):

```text
## Evento flagado pelo Detector

- **Template**: Failed password for <*> from <*> port 22 ssh2
- **Categoria**: brute_force
- **Regra disparada**: brute_force_by_ip_cardinality
- **Score**: 1.00
- **IPs únicos**: 20 (amostra: [203.0.113.10, 203.0.113.11, 203.0.113.12])
- **Usuários únicos**: 1 (amostra: [root])
- **Taxa média**: 0.67/min · **Pico**: 2.0/min
- **Janela**: 2026-04-18T10:00:01+00:00 → 2026-04-18T10:29:55+00:00
- **Observações do Detector**: 20 distinct source IPs over 20 failed events (ratio=1.00)

### Exemplos de linhas originais
1. Apr 18 10:00:01 server sshd[1001]: Failed password for root from 203.0.113.10 port 22 ssh2
```

## 4. O que NÃO é enviado ao LLM

Seção central para análise de privacidade:

- **O arquivo de log completo não é enviado.** Só templates e amostras dos eventos flagados saem da infra local; eventos normais (a maioria) nunca deixam o host.
- **Amostras limitadas a 3 entradas por evento**: 3 IPs, 3 usuários, até 3 linhas originais.
- **Sem mascaramento antes do envio**: IPs, usuários e conteúdo das linhas vão do jeito que estão nos logs crus. Pseudonimização é item de roadmap.
- **Nenhuma chave, secret ou variável de ambiente entra em qualquer prompt.** A `LLM_API_KEY` só viaja no header HTTP de autenticação.
- **Retenção** dos dados enviados é definida pelo provedor; consultar os Terms of Service vigentes do provedor configurado (ex.: Ollama Cloud, GLM Coding, OpenRouter).

Recomendação: quando os logs contiverem dados sensíveis e não houver DPA com o provedor, usar `--dry-run` para produzir o relatório estrutural sem chamar o modelo.

## 5. A resposta esperada

```json
{
  "explanation": "Ataque de força bruta contra a conta root a partir de 20 IPs distintos.",
  "severity": "high",
  "next_action": "Bloquear os IPs envolvidos via firewall e revisar logs de sessão anterior."
}
```

- `explanation`: 1-2 frases em pt-BR, 10–2000 caracteres.
- `severity`: enum — exatamente um de `low`, `medium`, `high`, `critical`.
- `next_action`: 1 frase em pt-BR, 5–500 caracteres.

## 6. Como a resposta é validada

Lógica em `src/lst/explainer/parser.py`:

- Tenta `json.loads()` direto após `strip()`; tolera markdown fences envolvendo o JSON.
- Se falha, fallback via regex `\{.*\}` (DOTALL) extrai o primeiro bloco `{...}` — útil contra prefixos como `"Aqui está o JSON:"`; logado em `WARNING`.
- Confere presença das três chaves (`explanation`, `severity`, `next_action`); normaliza `severity` para lowercase.
- Qualquer falha levanta `ValueError`. O orquestrador re-tenta a chamada até `LLM_PARSE_RETRIES` vezes (default 1) — rede de segurança contra respostas vazias ou truncadas devolvidas com `200 OK`, que a lib `openai` não retenta. Esgotadas as tentativas, loga em `ERROR` e move o evento para um rodapé **"Eventos não explicados"** no relatório, em vez de descartá-lo em silêncio. A validação final é feita pelo schema Pydantic `ExplainedEvent` antes de o Reporter receber o objeto.

## 7. Structured output: cascata adaptativa

O `OpenAICompatClient.complete` negocia o `response_format` conforme `LLM_STRUCTURED_MODE` (default `auto`):

1. **`json_schema`** — JSON Schema estrito (`strict: True`, `additionalProperties: False`, os três campos `required`). Força os campos obrigatórios no nível da API, eliminando o truncamento de campos visto em alguns provedores (ex.: GLM `glm-5.2`, que falhava com `json_object`, passou a entregar os eventos com `json_schema`).
2. **`json_object`** — o modo legado `{"type": "json_object"}`.
3. **`none`** — sem `response_format`; confia no system prompt + parser.

Em `auto`, o cliente tenta os três em ordem e desce **um nível por `BadRequestError` relacionado a `response_format`** — nunca parseia a mensagem de erro para adivinhar qual knob falhou (a redação varia por provedor). Fixar o modo (`json_schema` / `json_object` / `none`) desativa a cascata e propaga o erro. Em qualquer modo, o system prompt continua pedindo JSON literal e o parser da seção 6 tolera variações.

## 8. Parâmetros configuráveis

Parâmetros que afetam as chamadas ao LLM vivem em `.env`: `LLM_MODEL`, `LLM_STRUCTURED_MODE`, `LLM_PARSE_RETRIES`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `LLM_MAX_TOKENS`. Lista completa com faixas e defaults em [Configuration](../README.md#configuration). Trocar de modelo (`LLM_MODEL`) ou de provedor (`LLM_BASE_URL`) não exige alteração de código — o prompt e o parser são agnósticos a qual LLM responde, desde que o endpoint seja compatível com OpenAI.

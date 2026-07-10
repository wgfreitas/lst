# LST (Log Sec Triage)

> A triage assistant for security logs: reduces gigabytes of raw log data to dozens of explained, prioritized events in Brazilian Portuguese.

[![CI](https://github.com/wgfreitas/lst/actions/workflows/ci.yml/badge.svg)](https://github.com/wgfreitas/lst/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## What LST does

A security analyst handed a gigabyte of `auth.log` output cannot read it line by line. Traditional tools (`grep`, awk pipelines, heavyweight SIEMs) shift the burden back to the analyst: the human has to know what to search for before the tool helps. That assumption breaks on the first unfamiliar attack pattern.

LST inverts the flow. Template mining collapses the raw log into a few hundred recurring patterns. Deterministic rules isolate the subset of patterns that deviate from the observation window. A language model reads the flagged metrics and translates each one into operational Portuguese: *what this is, how serious it looks, what to do next*.

The result is a Markdown report an analyst reviews in minutes, not hours. Detection is 100% deterministic — the same input always flags the same events. Only the explanation layer uses an LLM, which keeps the audit trail intact regardless of model stochasticity.

## How it works

```
  Raw log file (auth.log / syslog, multi-GB)
        |
        v
  [1] Parser + Template Miner (drain3)
        |  streaming; ~hundreds of unique templates
        v
  [2] Aggregator
        |  per-template statistics (counts, rates, cardinalities)
        v
  [3] Rule-based Detector
        |  deterministic rules -> tens of flagged events
        v
  [4] LLM Explainer  <-- LLM provider (HTTPS, OpenAI-compatible)
        |  JSON: explanation, severity, next_action (pt-BR)
        v
  [5] Reporter
        |
        v
  Markdown triage report (pt-BR)
```

Each stage is isolated behind a Pydantic schema; stages communicate by passing frozen models, not implicit state. See the [Mermaid architecture diagram](docs/architecture.md) for the full picture.

1. **Parser + Template Miner** streams the log line by line and runs [drain3](https://github.com/IBM/Drain3) to cluster syntactically similar lines into templates.
2. **Aggregator** computes per-template statistics: total occurrences, mean and peak rate, unique IPs (IPv4 and IPv6) and users, sample IPs.
3. **Detector** runs a registry of rules (one file per rule). Each rule scores each template; the engine dedups by `(score, priority)` and emits the flagged events.
4. **Explainer** sends flagged events to the LLM and parses a strict JSON response into `ExplainedEvent` objects. Structured output is negotiated through a cascade — strict JSON Schema first, then `json_object`, then plain text — degrading only when the provider rejects a format; an empty or unparseable reply is re-requested before the event is set aside.
5. **Reporter** renders a Markdown document: severity-ordered events, per-event metrics tables, rule references, and an appendix listing every active detection rule.

## Key design principles

- **Deterministic detection, LLM only for explanation.** Rules are pure functions over aggregated statistics. The same log always produces the same flagged events, audit-trail intact.
- **Streaming I/O.** The parser never loads the full log into memory, so LST scales to multi-gigabyte files without tuning.
- **Offline-first.** Stages 1 through 3 run with zero network access. Only the Explainer requires outbound HTTPS.
- **Auditable rules.** Each detection rule lives in a single file under `src/lst/detector/rules/`. An analyst can read one file and understand one rule.
- **pt-BR output.** The report is written for a Brazilian SOC audience: explanations, severity labels, and next-action recommendations are all in Portuguese.

## Installation

```bash
git clone https://github.com/wgfreitas/lst.git
cd lst
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

The `[dev]` extra pulls the full development stack (tests, lint, type-check). For a runtime-only install, use `pip install -e .`.

## Quick start

Dry-run scan (skips the LLM, no API key required):

```bash
lst scan /var/log/auth.log --dry-run
```

Full scan (requires `LLM_API_KEY` in the environment or a local `.env` file; see [Configuration](#configuration)):

```bash
cp .env.example .env   # then edit .env and set LLM_API_KEY
lst scan /var/log/auth.log -o report.md
```

Run `lst --help` to list all commands. `lst version` prints the installed version.

## Sample output

Excerpt from a real run against the project fixture (`tests/fixtures/auth_sample.log`). See [docs/examples/sample_report.md](docs/examples/sample_report.md) for the full report.

```markdown
# Relatório de Triagem de Logs

- **Fonte**: `tests/fixtures/auth_sample.log`
- **Total de eventos**: 3

## Resumo por severidade

- 🔴 **Crítico**: 0
- 🟠 **Alto**: 2
- 🟡 **Médio**: 1
- 🟢 **Baixo**: 0

## 1. [HIGH] brute_force: Failed password for root from <*> port 22 ssh2

- **Severidade**: Alto
- **Categoria**: Brute Force
- **Regra**: `brute_force_by_ip_cardinality` (score 1.00)

### Métricas

| Métrica | Valor |
| --- | --- |
| Ocorrências totais | 20 |
| Taxa média (por minuto) | 0.67 |
| Pico (por minuto) | 2.00 |
| IPs únicos | 20 |

### Explicação

20 tentativas de login com falha em root provenientes de IPs distintos
indicam um ataque de força bruta em SSH.

### Próxima ação

Bloquear os IPs identificados e analisar logs de sessão anterior para
detecção de possíveis brechas.
```

The emoji distribution block, sample lines, and per-rule appendix are omitted from the excerpt. When the LLM cannot explain a flagged event (even after `LLM_PARSE_RETRIES`), the report ends with an **"Eventos não explicados"** footer listing those events, so coverage gaps are never silent.

## Architecture

LST is a 5-stage pipeline. Data flows in one direction; each stage depends only on the previous stage's output schema. The LLM lives in stage 4 and nowhere else: *detection is deterministic, explanation is stochastic*. This split is what makes the tool auditable.

See [docs/architecture.md](docs/architecture.md) for the Mermaid diagram with the full pipeline, external dependencies (the LLM provider, `.env`), and expected volumes at each stage.

The entry point is `lst.pipeline.run_pipeline`, an async coroutine that glues the five stages together. The CLI in `src/lst/cli.py` is intentionally thin — it handles flags, builds `Settings`, and maps known exceptions to pt-BR error messages with non-zero exit codes.

## Configuration

Configuration is read from the environment or a local `.env` file (loaded automatically by `pydantic-settings`). Field names are case-insensitive.

| Variable | Default | Range | Description |
| --- | --- | --- | --- |
| `LLM_API_KEY` | *(required)* | non-empty string | Bearer token for the LLM provider. Startup fails if unset unless `--dry-run` is passed. |
| `LLM_MODEL` | `gpt-oss:20b` | non-empty string | Model identifier understood by the configured provider (e.g. `glm-5.2` on GLM Coding). |
| `LLM_BASE_URL` | `https://ollama.com/v1` | non-empty string | OpenAI-compatible chat-completions base URL. Point it at any compatible provider. |
| `LLM_STRUCTURED_MODE` | `auto` | `auto` / `json_schema` / `json_object` / `none` | Structured-output strategy. `auto` tries strict JSON Schema, then `json_object`, then free text, degrading only when the provider rejects a format. |
| `LLM_PARSE_RETRIES` | `1` | `[0, 3]` | Extra attempts to re-request when the provider returns an empty or unparseable 200-OK reply. |
| `LLM_TIMEOUT_SECONDS` | `60.0` | `[1.0, 300.0]` | Per-request wall-clock timeout for a single call to the LLM. |
| `LLM_MAX_RETRIES` | `2` | `[0, 5]` | Automatic retry budget for transient HTTP failures (5xx, rate-limit). |
| `LLM_MAX_TOKENS` | `1024` | `[64, 4096]` | Hard cap on tokens the LLM may emit per response. The default leaves room for multi-sentence Portuguese explanations. |

> **Backward compatibility:** the legacy `OLLAMA_API_KEY`, `OLLAMA_MODEL`, and `OLLAMA_BASE_URL` names still work as aliases for the three `LLM_*` variables above, so a v1.0.0 `.env` keeps loading unchanged.

### Provider support

LST works with any endpoint that speaks the OpenAI-compatible chat-completions protocol. Only `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY` change between providers — no code edits. With `LLM_STRUCTURED_MODE=auto` (the default) the client adapts to each provider's structured-output support automatically — for example, GLM Coding's `glm-5.2` needs JSON Schema, which `auto` selects.

| Provider | `LLM_BASE_URL` | Example model |
| --- | --- | --- |
| Ollama Cloud (default) | `https://ollama.com/v1` | `gpt-oss:20b` |
| GLM Coding (Z.ai) | `https://api.z.ai/api/coding/paas/v4` | `glm-5.2` |
| OpenRouter | `https://openrouter.ai/api/v1` | `openai/gpt-4o-mini` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |

A template `.env.example` ships with the repository; copy it to `.env` and fill in the blanks.

## Detection rules

The detector runs a registry of rules defined in `src/lst/detector/rules/`. Each rule is a single file and can be toggled by editing `ACTIVE_RULES` in `rules/__init__.py`. Rule semantics are order-independent; the engine dedups results by `(score, priority)`.

| Rule ID | Category | What it flags |
| --- | --- | --- |
| `novelty_singleton` | `novelty` | Templates that appear only once in the observation window. |
| `brute_force_by_ip_cardinality` | `brute_force` | Many distinct source IPs converging on the same failure template. |
| `rate_spike_3sigma_or_absolute` | `spike` | Per-minute rate spikes that exceed both a 3-sigma threshold and an absolute floor. |
| `high_risk_keyword_match` | `high_risk_pattern` | Known high-risk IOC keywords (for example, `POSSIBLE BREAK-IN ATTEMPT`). |
| `source_variety_no_auth_context` | `variety` | Fan-in of many IPs on a template that has no explicit authentication verb. |

The Portuguese description that ships in every generated report comes from the rule's `description_pt` field. Detailed scoring formulas and tuning knobs per rule are documented in [docs/detection_rules.md](docs/detection_rules.md).

## Limitations and roadmap

LST is a small, honest tool. The following limitations are known and tracked:

- **Sequential LLM calls.** The Explainer processes flagged events one at a time. Concurrency will land once rate-limit back-off is validated against the target endpoint.
- **Stochastic severity.** Severity and next-action text come from the LLM and can vary between runs for the same input. Detection and scoring do not.
- **Stateless.** Every run is independent. There is no database, no run history, no diff between consecutive scans.
- **Single log format.** The parser and regex extractors target `auth.log`-style syslog. Structured-JSON ingestion is on the roadmap.

## How AI accelerated this project

This section addresses the laboratory ebook requirement in section 4.3.1.

**Tool.** [Claude Code](https://www.anthropic.com/claude-code) (Anthropic) was used throughout the project for the bulk of implementation work. The project was conceived as an experiment in AI-assisted development for a generative-AI lab course, so AI involvement is deliberate and documented rather than hidden.

**Where AI helped most.** Initial scaffolding (`pyproject.toml`, the Typer CLI skeleton, Pydantic schema boilerplate), test fixture generation (for example, the `FakeLLMClient` that isolates HTTP mocking from engine tests), and iterative prompt engineering for the Explainer. Claude Code carried the tedium of boilerplate and repetitive structure, leaving design judgment to the developer.

**Where AI was actively challenged.** Several first-draft suggestions were rejected and refined after review:

- The initial dependency list named `pydantic-settings[dotenv]`, a nonexistent extra — `python-dotenv` is already bundled.
- The `SpikeRule` draft triggered on an OR between a 3-sigma test and an absolute floor, which produced false positives on sparse logs. The final rule requires both tests to agree.
- Event-header truncation defaulted to 80 characters (a VT100-era width) and cut `POSSIBLE BREAK-IN ATTEMPT!` mid-phrase in the report. A smoke test against real Ollama Cloud output surfaced the bug; the limit was raised to 120 in phase 7.2.
- LLM responses truncated mid-sentence in phase 7.1 because `max_tokens` was not set; the model inherited a conservative default. Fixed by exposing `LLM_MAX_TOKENS` as a configuration knob.

**Why the result is maintainable despite AI involvement.** Every phase followed the same loop: written specification, explicit architectural decisions, implementation, tests that validate behavior rather than implementation details, manual review of each diff. Public naming, pt-BR output strings, and rule semantics were decided by the developer. The test suite (181 tests, 96% branch coverage) provides the regression safety net that lets future changes proceed without re-reading every file.

## Development

Common developer tasks are wrapped in the `Makefile`; run `make help` to list every target.

- `make install` — editable install with the full dev dependency group.
- `make test` — run the pytest suite with coverage. Fails under 70% total coverage.
- `make lint` — run `ruff check` against the whole tree.
- `make format` — run `ruff format` in place.
- `make typecheck` — run `mypy --strict` against `src/`.
- `make clean` — remove build artifacts and tool caches.

The project targets Python 3.11 and is validated against the pinned dependency ranges in `pyproject.toml`.

## License

Released under the [MIT License](LICENSE).

## Acknowledgments

- [drain3](https://github.com/IBM/Drain3) — log template mining, originally from the LogPAI group at IBM Research.
- [Ollama](https://ollama.com) — the default hosted inference endpoint for the Explainer stage; any OpenAI-compatible provider works.
- **Laboratório Introdutório: Construindo um Miniprojeto com Inteligência Artificial Generativa** (AKCIT / UFG, 2026) — the course context under which this project was developed.

---

> 🇧🇷 **Read this in Portuguese below** / Leia a versão em português abaixo

---

<details>
<summary>🇧🇷 Versão em português (clique para expandir)</summary>

## LST — Triagem de Logs de Segurança

> Assistente de triagem de logs de segurança: reduz gigabytes de logs brutos a dezenas de eventos explicados e priorizados em português brasileiro.

## O que o LST faz

Um analista de segurança diante de um gigabyte de `auth.log` não consegue inspecionar linha a linha. Ferramentas tradicionais (`grep`, pipelines de awk, SIEMs pesados) transferem o trabalho de volta ao analista: o humano precisa saber o que procurar antes que a ferramenta ajude. Essa premissa falha no primeiro padrão de ataque desconhecido.

O LST inverte o fluxo. Template mining colapsa o log bruto em algumas centenas de padrões recorrentes. Regras determinísticas isolam o subconjunto de padrões que destoa da janela de observação. Um modelo de linguagem lê as métricas dos eventos marcados e traduz cada um em português operacional: *o que é, quão grave parece, qual a próxima ação*.

O resultado é um relatório em Markdown que um analista revisa em minutos, não em horas. A detecção é 100% determinística — a mesma entrada sempre marca os mesmos eventos. Apenas a camada de explicação usa um LLM, o que preserva a trilha de auditoria independentemente da estocasticidade do modelo.

## Como funciona

```
  Arquivo de log bruto (auth.log / syslog, múltiplos GB)
        |
        v
  [1] Parser + Template Miner (drain3)
        |  streaming; ~centenas de templates únicos
        v
  [2] Aggregator
        |  estatísticas por template (contagens, taxas, cardinalidades)
        v
  [3] Detector baseado em regras
        |  regras determinísticas -> dezenas de eventos marcados
        v
  [4] Explainer (LLM)  <-- Provedor LLM (HTTPS, compatível com OpenAI)
        |  JSON: explicação, severidade, próxima ação (pt-BR)
        v
  [5] Reporter
        |
        v
  Relatório de triagem em Markdown (pt-BR)
```

Cada estágio é isolado por trás de um schema Pydantic; os estágios se comunicam passando modelos imutáveis, não estado implícito. Consultar o [diagrama Mermaid de arquitetura](docs/architecture.md) para o quadro completo.

1. **Parser + Template Miner** lê o log linha a linha por streaming e executa o [drain3](https://github.com/IBM/Drain3) para agrupar linhas sintaticamente similares em templates.
2. **Aggregator** calcula estatísticas por template: total de ocorrências, taxa média e de pico, cardinalidades de IPs (IPv4 e IPv6) e usuários, amostras de IPs.
3. **Detector** executa um registro de regras (um arquivo por regra). Cada regra pontua cada template; o motor deduplica por `(score, priority)` e emite os eventos marcados.
4. **Explainer** envia os eventos marcados ao LLM e analisa a resposta JSON estrita em objetos `ExplainedEvent`. O structured output é negociado por uma cascata — JSON Schema estrito primeiro, depois `json_object`, depois texto livre — degradando só quando o provedor rejeita um formato; uma resposta vazia ou inválida é re-solicitada antes de o evento ser posto de lado.
5. **Reporter** produz o documento Markdown: eventos ordenados por severidade, tabelas de métricas por evento, referências de regras e um apêndice listando cada regra de detecção ativa.

## Princípios de projeto

- **Detecção determinística, LLM apenas para explicação.** As regras são funções puras sobre estatísticas agregadas. O mesmo log sempre gera os mesmos eventos marcados, com a trilha de auditoria intacta.
- **I/O por streaming.** O parser nunca carrega o log inteiro em memória, o que permite ao LST processar arquivos de múltiplos gigabytes sem ajustes.
- **Funciona offline.** Os estágios 1 a 3 rodam sem qualquer acesso à rede. Apenas o Explainer depende de HTTPS saindo.
- **Regras auditáveis.** Cada regra de detecção vive em um único arquivo em `src/lst/detector/rules/`. Um analista lê um arquivo e entende uma regra.
- **Saída em pt-BR.** O relatório é escrito para o público brasileiro de SOC: explicações, rótulos de severidade e recomendações de próxima ação estão todos em português.

## Instalação

```bash
git clone https://github.com/wgfreitas/lst.git
cd lst
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

O extra `[dev]` traz a stack de desenvolvimento completa (testes, lint, type-check). Para instalar apenas o runtime, basta `pip install -e .`.

## Primeiros passos

Scan em modo dry-run (pula o LLM, dispensa API key):

```bash
lst scan /var/log/auth.log --dry-run
```

Scan completo (exige `LLM_API_KEY` no ambiente ou em um `.env` local; ver [Configuração](#configuração)):

```bash
cp .env.example .env   # em seguida, editar .env e definir LLM_API_KEY
lst scan /var/log/auth.log -o report.md
```

O comando `lst --help` lista todos os subcomandos. `lst version` imprime a versão instalada.

## Exemplo de saída

Trecho de uma execução real contra o fixture do projeto (`tests/fixtures/auth_sample.log`). Consultar [docs/examples/sample_report.md](docs/examples/sample_report.md) para o relatório completo.

```markdown
# Relatório de Triagem de Logs

- **Fonte**: `tests/fixtures/auth_sample.log`
- **Total de eventos**: 3

## Resumo por severidade

- 🔴 **Crítico**: 0
- 🟠 **Alto**: 2
- 🟡 **Médio**: 1
- 🟢 **Baixo**: 0

## 1. [HIGH] brute_force: Failed password for root from <*> port 22 ssh2

- **Severidade**: Alto
- **Categoria**: Brute Force
- **Regra**: `brute_force_by_ip_cardinality` (score 1.00)

### Métricas

| Métrica | Valor |
| --- | --- |
| Ocorrências totais | 20 |
| Taxa média (por minuto) | 0.67 |
| Pico (por minuto) | 2.00 |
| IPs únicos | 20 |

### Explicação

20 tentativas de login com falha em root provenientes de IPs distintos
indicam um ataque de força bruta em SSH.

### Próxima ação

Bloquear os IPs identificados e analisar logs de sessão anterior para
detecção de possíveis brechas.
```

O bloco de distribuição com emojis, as linhas de amostra e o apêndice por regra foram omitidos neste trecho. Quando o LLM não consegue explicar um evento marcado (mesmo após `LLM_PARSE_RETRIES`), o relatório termina com um rodapé **"Eventos não explicados"** que lista esses eventos, para que lacunas de cobertura nunca fiquem silenciosas.

## Arquitetura

O LST é um pipeline de 5 estágios. Os dados fluem em sentido único; cada estágio depende apenas do schema de saída do estágio anterior. O LLM vive no estágio 4 e em nenhum outro lugar: *a detecção é determinística, a explicação é estocástica*. Essa separação é o que torna a ferramenta auditável.

Consultar [docs/architecture.md](docs/architecture.md) para o diagrama Mermaid com o pipeline completo, as dependências externas (o provedor LLM, `.env`) e os volumes esperados em cada estágio.

O ponto de entrada é `lst.pipeline.run_pipeline`, uma coroutine async que costura os cinco estágios. A CLI em `src/lst/cli.py` é deliberadamente enxuta — trata flags, constrói `Settings` e mapeia exceções conhecidas para mensagens de erro em pt-BR com códigos de saída não-zero.

## Configuração

A configuração é lida do ambiente ou de um `.env` local (carregado automaticamente pelo `pydantic-settings`). Os nomes de campo são case-insensitive.

| Variável | Padrão | Faixa | Descrição |
| --- | --- | --- | --- |
| `LLM_API_KEY` | *(obrigatório)* | string não-vazia | Token de autenticação do provedor LLM. A inicialização falha se não estiver definido, exceto quando `--dry-run` é usado. |
| `LLM_MODEL` | `gpt-oss:20b` | string não-vazia | Identificador do modelo entendido pelo provedor configurado (ex.: `glm-5.2` no GLM Coding). |
| `LLM_BASE_URL` | `https://ollama.com/v1` | string não-vazia | URL base da API de chat-completions compatível com OpenAI. Aponte para qualquer provedor compatível. |
| `LLM_STRUCTURED_MODE` | `auto` | `auto` / `json_schema` / `json_object` / `none` | Estratégia de structured output. `auto` tenta JSON Schema estrito, depois `json_object`, depois texto livre, degradando só quando o provedor rejeita um formato. |
| `LLM_PARSE_RETRIES` | `1` | `[0, 3]` | Tentativas extras de re-requisição quando o provedor devolve resposta vazia ou inválida com 200 OK. |
| `LLM_TIMEOUT_SECONDS` | `60.0` | `[1.0, 300.0]` | Timeout wall-clock de uma única chamada ao LLM, em segundos. |
| `LLM_MAX_RETRIES` | `2` | `[0, 5]` | Orçamento de retry automático para falhas HTTP transitórias (5xx, rate-limit). |
| `LLM_MAX_TOKENS` | `1024` | `[64, 4096]` | Teto de tokens que o LLM pode emitir por resposta. O padrão dá margem para explicações em português de múltiplas frases sem truncamento. |

> **Retrocompatibilidade:** os nomes legados `OLLAMA_API_KEY`, `OLLAMA_MODEL` e `OLLAMA_BASE_URL` continuam funcionando como aliases das três variáveis `LLM_*` acima, então um `.env` da v1.0.0 segue carregando sem alteração.

### Suporte a provedores

O LST funciona com qualquer endpoint que fale o protocolo de chat-completions compatível com OpenAI. Só `LLM_BASE_URL`, `LLM_MODEL` e `LLM_API_KEY` mudam entre provedores — sem editar código. Com `LLM_STRUCTURED_MODE=auto` (o padrão), o cliente se adapta automaticamente ao suporte de structured output de cada provedor — por exemplo, o `glm-5.2` do GLM Coding precisa de JSON Schema, que o `auto` seleciona.

| Provedor | `LLM_BASE_URL` | Modelo de exemplo |
| --- | --- | --- |
| Ollama Cloud (padrão) | `https://ollama.com/v1` | `gpt-oss:20b` |
| GLM Coding (Z.ai) | `https://api.z.ai/api/coding/paas/v4` | `glm-5.2` |
| OpenRouter | `https://openrouter.ai/api/v1` | `openai/gpt-4o-mini` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |

Um template `.env.example` acompanha o repositório; basta copiá-lo para `.env` e preencher os valores.

## Regras de detecção

O Detector executa um registro de regras definido em `src/lst/detector/rules/`. Cada regra é um único arquivo e pode ser desativada editando `ACTIVE_RULES` em `rules/__init__.py`. A semântica é independente da ordem; o motor deduplica resultados por `(score, priority)`.

| ID da regra | Categoria | O que marca |
| --- | --- | --- |
| `novelty_singleton` | `novelty` | Templates que aparecem uma única vez na janela de observação. |
| `brute_force_by_ip_cardinality` | `brute_force` | Muitos IPs de origem distintos convergindo no mesmo template de falha. |
| `rate_spike_3sigma_or_absolute` | `spike` | Picos de taxa por minuto que ultrapassam tanto um limiar 3-sigma quanto um piso absoluto. |
| `high_risk_keyword_match` | `high_risk_pattern` | Palavras-chave de IOC conhecidamente de alto risco (por exemplo, `POSSIBLE BREAK-IN ATTEMPT`). |
| `source_variety_no_auth_context` | `variety` | Fan-in de muitos IPs sobre um template sem verbo de autenticação explícito. |

A descrição em português que aparece em todo relatório gerado vem do campo `description_pt` da regra. Fórmulas detalhadas de scoring e knobs de ajuste por regra estão documentadas em [docs/detection_rules.md](docs/detection_rules.md).

## Limitações e roadmap

O LST é uma ferramenta enxuta e transparente sobre suas limitações. As pendências conhecidas e rastreadas:

- **Chamadas LLM sequenciais.** O Explainer processa os eventos marcados um de cada vez. A concorrência entra no código depois que o back-off de rate-limit for validado contra o endpoint alvo.
- **Severidade estocástica.** A severidade e o texto da próxima ação vêm do LLM e podem variar entre execuções para a mesma entrada. A detecção e o scoring não variam.
- **Sem persistência.** Cada execução é independente. Não há banco de dados, histórico de runs, nem diff entre scans consecutivos.
- **Formato único de log.** O parser e os extratores de regex miram syslog no estilo `auth.log`. Ingestão de JSON estruturado está no roadmap.

## Como a IA acelerou este projeto

Esta seção atende ao requisito da seção 4.3.1 do ebook do laboratório.

**Ferramenta.** O [Claude Code](https://www.anthropic.com/claude-code) (Anthropic) foi usado ao longo do projeto para a maior parte do trabalho de implementação. O projeto foi concebido como experimento de desenvolvimento assistido por IA para um curso de laboratório de IA generativa, portanto o uso de IA é deliberado e documentado, não escondido.

**Onde a IA ajudou mais.** Scaffolding inicial (`pyproject.toml`, esqueleto da CLI em Typer, boilerplate de schemas Pydantic), geração de fixtures de teste (por exemplo, o `FakeLLMClient` que isola o mock HTTP dos testes do motor) e engenharia iterativa de prompt para o Explainer. O Claude Code absorveu a tediosa repetição de estrutura, deixando o julgamento de projeto para o desenvolvedor.

**Onde a IA foi ativamente desafiada.** Várias propostas de primeira iteração foram rejeitadas e refinadas após revisão:

- A lista inicial de dependências trazia `pydantic-settings[dotenv]`, um extra inexistente — o `python-dotenv` já vem embutido transitivamente.
- O rascunho do `SpikeRule` disparava num OR entre um teste 3-sigma e um piso absoluto, o que gerava falsos-positivos em logs esparsos. A versão final exige que os dois testes concordem.
- O truncamento de cabeçalho de evento ficou inicialmente em 80 caracteres (herança da largura VT100) e cortava `POSSIBLE BREAK-IN ATTEMPT!` no meio do relatório. Um smoke test contra a saída real do Ollama Cloud revelou o bug; o limite foi elevado para 120 na fase 7.2.
- As respostas do LLM foram truncadas no meio da frase na fase 7.1 porque `max_tokens` não estava definido; o modelo herdava um padrão conservador. Corrigido expondo `LLM_MAX_TOKENS` como knob de configuração.

**Por que o resultado é mantível apesar do envolvimento da IA.** Cada fase seguiu o mesmo loop: especificação escrita, decisões arquiteturais explícitas, implementação, testes que validam comportamento (e não detalhes de implementação) e revisão manual de cada diff. Nomes públicos, strings de saída em pt-BR e a semântica das regras foram decididos pelo desenvolvedor. A suíte de testes (181 testes, 96% de cobertura de branches) fornece a rede de segurança que permite mudanças futuras sem reler cada arquivo.

## Desenvolvimento

As tarefas comuns de desenvolvimento estão encapsuladas no `Makefile`; `make help` lista todos os targets.

- `make install` — instalação editável com o grupo completo de dependências de dev.
- `make test` — executa o pytest com cobertura. Falha abaixo de 70% de cobertura total.
- `make lint` — roda `ruff check` em toda a árvore.
- `make format` — roda `ruff format` in-place.
- `make typecheck` — roda `mypy --strict` contra `src/`.
- `make clean` — remove artefatos de build e caches de ferramentas.

O projeto mira Python 3.11 e é validado contra as faixas de dependência fixadas em `pyproject.toml`.

## Licença

Distribuído sob a [Licença MIT](LICENSE).

## Agradecimentos

- [drain3](https://github.com/IBM/Drain3) — template mining de logs, originalmente do grupo LogPAI na IBM Research.
- [Ollama](https://ollama.com) — endpoint de inferência hospedado padrão do estágio Explainer; qualquer provedor compatível com OpenAI funciona.
- **Laboratório Introdutório: Construindo um Miniprojeto com Inteligência Artificial Generativa** (AKCIT / UFG, 2026) — contexto do curso no qual este projeto foi desenvolvido.

</details>

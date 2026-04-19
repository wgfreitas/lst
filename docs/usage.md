# Uso do LST

Este guia cobre a operação prática do LST após a instalação. Para posicionamento e arquitetura, consultar o [README](../README.md). Para detalhes de scoring das regras, consultar [detection_rules.md](detection_rules.md).

## Comandos disponíveis

O CLI expõe dois comandos:

```bash
lst scan LOG_PATH [-o OUTPUT] [--dry-run] [--verbose]
lst version
```

| Argumento / Flag | Descrição                                              |
| ---------------- | ------------------------------------------------------ |
| `LOG_PATH`       | Caminho do arquivo de log (obrigatório, posicional).   |
| `-o, --output`   | Grava o Markdown no arquivo indicado em vez de stdout. |
| `--dry-run`      | Pula o LLM e produz relatório com placeholders neutros. |
| `-v, --verbose`  | Ativa logs INFO para acompanhar o pipeline.            |

O subcomando `lst version` imprime a versão instalada e encerra.

## Exemplos de uso

### Cenário A — triagem rápida sem custo de LLM

```bash
lst scan /var/log/auth.log --dry-run
```

Útil para validar o pipeline, estimar tempo de execução e conferir parsing antes de gastar tokens do Ollama Cloud.

### Cenário B — triagem completa gravando em arquivo

```bash
cp .env.example .env   # configurar OLLAMA_API_KEY
lst scan /var/log/auth.log -o /tmp/report.md
```

O relatório Markdown vai para `/tmp/report.md`; stdout permanece silencioso, o que facilita encadear o comando em pipelines Unix.

### Cenário C — depuração com verbose

```bash
lst scan /var/log/auth.log --verbose --dry-run
```

O modo `--verbose` imprime cada estágio do pipeline concluindo (Parser, Template Miner, Aggregator, Detector, Explainer, Reporter), o que facilita identificar gargalos em logs grandes.

## Interpretando o relatório

O Markdown gerado segue sempre a mesma estrutura:

- **Cabeçalho**: fonte, timestamp em ISO-8601 e total de eventos marcados.
- **Resumo por severidade**: contagem por nível (🔴 Crítico, 🟠 Alto, 🟡 Médio, 🟢 Baixo).
- **Eventos**: ordenados por severidade decrescente e, em empate, por score decrescente.
- **Apêndice**: lista das regras de detecção ativas com descrição curta.

Cada evento traz, em ordem: cabeçalho com categoria e regra disparada, severidade, janela de ocorrência, tabela de métricas (ocorrências totais, taxa média e de pico, cardinalidades de IPs e usuários, amostras), explicação em pt-BR produzida pelo LLM, próxima ação recomendada e as linhas originais do log.

O relatório já vem priorizado — basta ler de cima para baixo e tratar os eventos na ordem apresentada.

## Códigos de saída

| Exit code | Significado                                                    |
| --------- | -------------------------------------------------------------- |
| `0`       | Sucesso: relatório gerado (mesmo que nenhum evento marcado).   |
| `1`       | Erro operacional (autenticação, timeout, validação de config). |
| `2`       | Erro de uso (arquivo não encontrado, argumento inválido).      |

Útil para scripting: um cron job que executa `lst scan` pode despachar o relatório por e-mail somente quando o exit code for `0`.

## Configuração via .env

A configuração vive em `.env` (ou em variáveis de ambiente). A lista completa de variáveis, padrões e faixas válidas está no [README](../README.md#configuration).

Para um setup mínimo, basta definir `OLLAMA_API_KEY`:

```ini
OLLAMA_API_KEY=sk-ollama-...
```

As demais variáveis têm padrões sensatos. Em `--dry-run`, nem a chave é necessária.

## Casos comuns e soluções

### `Erro: arquivo não encontrado`

O path não existe ou está fora do escopo de leitura. Verificar com `ls -la` antes de rodar, ou usar um caminho absoluto.

### `Erro: OLLAMA_API_KEY não configurada no .env`

A variável está ausente. Executar `cp .env.example .env` e editar o arquivo para preencher a chave. Em `--dry-run` a chave é dispensável.

### `Erro de autenticação no Ollama Cloud`

A chave existe mas é inválida ou expirou. Regenerar em https://ollama.com e atualizar o `.env`.

### `Timeout ao consultar o LLM`

O modelo demorou mais que `LLM_TIMEOUT_SECONDS` (padrão 60s). Para modelos grandes ou lotes com muitos eventos marcados, aumentar o valor no `.env`:

```ini
LLM_TIMEOUT_SECONDS=120
```

## Limitações operacionais

Para limitações conhecidas e roadmap, consultar a seção [Limitations and roadmap](../README.md#limitations-and-roadmap) do README. Em resumo: IPv4 apenas, chamadas LLM sequenciais, severidade estocástica.

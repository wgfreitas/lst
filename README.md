# LST (Log Sec Triage)

> A triage assistant for security logs: reduces gigabytes of raw log data to dozens of explained, prioritized events in Brazilian Portuguese.

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
  [4] LLM Explainer  <-- Ollama Cloud (HTTPS, OpenAI-compatible)
        |  JSON: explanation, severity, next_action (pt-BR)
        v
  [5] Reporter
        |
        v
  Markdown triage report (pt-BR)
```

Each stage is isolated behind a Pydantic schema; stages communicate by passing frozen models, not implicit state. See the [Mermaid architecture diagram](docs/architecture.md) for the full picture.

1. **Parser + Template Miner** streams the log line by line and runs [drain3](https://github.com/IBM/Drain3) to cluster syntactically similar lines into templates.
2. **Aggregator** computes per-template statistics: total occurrences, mean and peak rate, unique IPs and users, sample IPs.
3. **Detector** runs a registry of rules (one file per rule). Each rule scores each template; the engine dedups by `(score, priority)` and emits the flagged events.
4. **Explainer** sends flagged events to the LLM and parses a strict JSON response into `ExplainedEvent` objects. The client retries without `response_format=json_object` if the model rejects structured mode.
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

Full scan (requires `OLLAMA_API_KEY` in the environment or a local `.env` file; see [Configuration](#configuration)):

```bash
cp .env.example .env   # then edit .env and set OLLAMA_API_KEY
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

The emoji distribution block, sample lines, and per-rule appendix are omitted from the excerpt.

## Architecture

LST is a 5-stage pipeline. Data flows in one direction; each stage depends only on the previous stage's output schema. The LLM lives in stage 4 and nowhere else: *detection is deterministic, explanation is stochastic*. This split is what makes the tool auditable.

See [docs/architecture.md](docs/architecture.md) for the Mermaid diagram with the full pipeline, external dependencies (Ollama Cloud, `.env`), and expected volumes at each stage.

The entry point is `lst.pipeline.run_pipeline`, an async coroutine that glues the five stages together. The CLI in `src/lst/cli.py` is intentionally thin — it handles flags, builds `Settings`, and maps known exceptions to pt-BR error messages with non-zero exit codes.

## Configuration

Configuration is read from the environment or a local `.env` file (loaded automatically by `pydantic-settings`). Field names are case-insensitive.

| Variable | Default | Range | Description |
| --- | --- | --- | --- |
| `OLLAMA_API_KEY` | *(required)* | non-empty string | Bearer token for Ollama Cloud. Startup fails if unset unless `--dry-run` is passed. |
| `OLLAMA_MODEL` | `gpt-oss:20b` | non-empty string | Model identifier available on the caller's Ollama Cloud plan. |
| `OLLAMA_BASE_URL` | `https://ollama.com/v1` | non-empty string | OpenAI-compatible chat-completions base URL. Override only when pointing at a self-hosted proxy. |
| `LLM_TIMEOUT_SECONDS` | `60.0` | `[1.0, 300.0]` | Per-request wall-clock timeout for a single call to the LLM. |
| `LLM_MAX_RETRIES` | `2` | `[0, 5]` | Automatic retry budget for transient failures (HTTP 5xx, rate-limit). |
| `LLM_MAX_TOKENS` | `1024` | `[64, 4096]` | Hard cap on tokens the LLM may emit per response. The default leaves room for multi-sentence Portuguese explanations. |

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

- **IPv4-only.** The IP extractor does not parse IPv6 addresses. IPv6 support is on the roadmap.
- **Sequential LLM calls.** The Explainer processes flagged events one at a time. Concurrency will land once rate-limit back-off is validated against the target endpoint.
- **Stochastic severity.** Severity and next-action text come from the LLM and can vary between runs for the same input. Detection and scoring do not.
- **Stateless.** Every run is independent. There is no database, no run history, no diff between consecutive scans.
- **Single log format.** The parser and regex extractors target `auth.log`-style syslog. Structured-JSON ingestion is on the roadmap.
- **No CI/CD.** Tests are run manually via `make test` or `pytest`. Automated CI is not yet configured.

## How AI accelerated this project

This section addresses the laboratory ebook requirement in section 4.3.1.

**Tool.** [Claude Code](https://www.anthropic.com/claude-code) (Anthropic) was used throughout the project for the bulk of implementation work. The project was conceived as an experiment in AI-assisted development for a generative-AI lab course, so AI involvement is deliberate and documented rather than hidden.

**Where AI helped most.** Initial scaffolding (`pyproject.toml`, the Typer CLI skeleton, Pydantic schema boilerplate), test fixture generation (for example, the `FakeLLMClient` that isolates HTTP mocking from engine tests), and iterative prompt engineering for the Explainer. Claude Code carried the tedium of boilerplate and repetitive structure, leaving design judgment to the developer.

**Where AI was actively challenged.** Several first-draft suggestions were rejected and refined after review:

- The initial dependency list named `pydantic-settings[dotenv]`, a nonexistent extra — `python-dotenv` is already bundled.
- The `SpikeRule` draft triggered on an OR between a 3-sigma test and an absolute floor, which produced false positives on sparse logs. The final rule requires both tests to agree.
- Event-header truncation defaulted to 80 characters (a VT100-era width) and cut `POSSIBLE BREAK-IN ATTEMPT!` mid-phrase in the report. A smoke test against real Ollama Cloud output surfaced the bug; the limit was raised to 120 in phase 7.2.
- LLM responses truncated mid-sentence in phase 7.1 because `max_tokens` was not set; the model inherited a conservative default. Fixed by exposing `LLM_MAX_TOKENS` as a configuration knob.

**Why the result is maintainable despite AI involvement.** Every phase followed the same loop: written specification, explicit architectural decisions, implementation, tests that validate behavior rather than implementation details, manual review of each diff. Public naming, pt-BR output strings, and rule semantics were decided by the developer. The test suite (167 tests, 95.99% branch coverage) provides the regression safety net that lets future changes proceed without re-reading every file.

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
- [Ollama](https://ollama.com) — hosted inference endpoint used by the Explainer stage.
- **Laboratório Introdutório: Construindo um Miniprojeto com Inteligência Artificial Generativa** (AKCIT / UFG, 2026) — the course context under which this project was developed.

---

> 🇧🇷 **Read this in Portuguese below** / Leia a versão em português abaixo

---

<!-- pt-BR version will be added by prompt 10.2 -->

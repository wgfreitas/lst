# Regras de detecção

Este documento descreve as 5 regras determinísticas que o Detector executa sobre cada `AggregatedTemplate` emitido pelo Aggregator. Todas as regras são puras (sem I/O, sem estado), vivem em `src/lst/detector/rules/` e são listadas em `ACTIVE_RULES`. O LLM é usado apenas para explicar eventos já classificados — a decisão de severidade é determinística e auditável.

Para a visão geral do pipeline, consultar o [README](../README.md). Para operação do CLI, consultar [usage.md](usage.md).

## Conceitos básicos

**Template** — forma canônica produzida pelo drain3 ao substituir tokens variáveis por `<*>`. Ex.: `Failed password for <*> from <*> port <*> ssh2`.

**AggregatedTemplate** — agregação por `cluster_id` (um template) ao longo da janela: `total_count`, `unique_ips`, `unique_users`, `rate_per_minute`, `peak_rate_per_minute`, amostras e janela temporal (`first_seen` → `last_seen`).

**Score** — real em `[0.0, 1.0]` atribuído pela regra. Regras que medem magnitude (brute force, variety, spike) calculam o score por saturação (mais sinal → score mais alto, até o teto 1.0). Regras binárias (novelty, high-risk) usam valores fixos.

**Deduplicação por cluster** — no máximo um `FlaggedEvent` é emitido por `cluster_id`. Quando múltiplas regras disparam sobre o mesmo cluster, o engine escolhe pelo par `(score, prioridade)` em ordem decrescente. O score domina; a prioridade só desempata.

Prioridade das categorias (só pesa em empates):

| Categoria | Prioridade |
| --- | --- |
| `BRUTE_FORCE` | 5 |
| `HIGH_RISK_PATTERN` | 4 |
| `NOVELTY` | 3 |
| `SPIKE` | 2 |
| `VARIETY` | 1 |

Exemplo: um evento com score 0.81 em `BRUTE_FORCE` perde para outro com score 0.82 em `NOVELTY`. Mas dois eventos em 0.80 resolvem pela prioridade — `BRUTE_FORCE` vence.

## Visão geral

| Regra | Categoria | Prioridade | Score | Quando dispara |
| --- | --- | --- | --- | --- |
| `brute_force_by_ip_cardinality` | `BRUTE_FORCE` | 5 | 0.50–1.00 | 10+ IPs distintos, razão IP/total ≥ 0.8, verbo de falha |
| `high_risk_keyword_match` | `HIGH_RISK_PATTERN` | 4 | 0.80 fixo | Template ou amostra casa um IOC conhecido |
| `novelty_singleton` | `NOVELTY` | 3 | 0.60 ou 0.90 | `total_count == 1` (0.90 se também IOC) |
| `rate_spike_3sigma_or_absolute` | `SPIKE` | 2 | até 1.00 | Pico ≥ 5/min **ou** pico ≥ 3× média (com piso de 3/min), `total_count ≥ 3` |
| `source_variety_no_auth_context` | `VARIETY` | 1 | 0.17–1.00 | 5+ IPs, razão ≥ 0.5, sem verbo de auth |

## `brute_force_by_ip_cardinality`

- **Arquivo**: `src/lst/detector/rules/brute_force.py`
- **Categoria**: `BRUTE_FORCE` (prioridade 5)
- **Captura**: muitos IPs distintos falhando contra o mesmo template — a fingerprint clássica de força bruta em SSH.

**Critérios (todos obrigatórios)**:

- `unique_ips >= 10`
- `total_count > 0`
- `unique_ips / total_count >= 0.8` (a maior parte das linhas tem IP único)
- Template casa `FAIL_VERBS_RE`: `fail|failed|invalid|denied|reject|rejected`

**Score**: `min(1.0, unique_ips / 20.0)`. Satura em 20 IPs distintos — 10 IPs = 0.50, 15 IPs = 0.75, 20+ IPs = 1.00.

**Racional dos thresholds**: o gate de razão 0.8 evita falso positivo em logs onde poucos IPs dominam (ex.: 50 falhas, 3 IPs). O gate de `FAIL_VERBS_RE` exclui fan-ins benignos — health checks de load balancer naturalmente atingem muitos IPs sem serem falhas.

**Dispara em**: `Failed password for root from <*> port 22 ssh2` com 20 IPs distintos em 20 linhas.
**NÃO dispara em**: `Accepted publickey for <*>` com 20 IPs — é sucesso, não falha.

## `high_risk_keyword_match`

- **Arquivo**: `src/lst/detector/rules/high_risk.py`
- **Categoria**: `HIGH_RISK_PATTERN` (prioridade 4)
- **Captura**: ocorrências literais de IOCs e alertas conhecidos no template ou nas `sample_lines`.

**Critérios**: template ou qualquer `sample_line` casa um dos padrões de `HIGH_RISK_PATTERNS` (avaliação case-insensitive):

| Tag | Regex |
| --- | --- |
| `break_in_attempt` | `POSSIBLE\s+BREAK-IN\s+ATTEMPT` |
| `possible_attack` | `possible\s+attack` |
| `kernel_panic` | `\bkernel\s+panic\b` |
| `sudo_denied` | `sudo:.*(?:NOT\s+in\s+sudoers\|command\s+not\s+allowed)` |
| `auth_failure` | `\bauthentication\s+failure\b` |
| `root_login` | `\broot\s+login\b` |
| `unauthorized` | `\bunauthorized\b\|\bunauthorised\b` |
| `malware_keyword` | `\b(?:malware\|trojan\|rootkit\|backdoor)\b` |

O template é testado primeiro; se não casar, as `sample_lines` são varridas. A tag que casou entra em `context_notes` para rastreabilidade.

**Score**: fixo em `0.8`. A regra não avalia magnitude — presença basta. Frequência entra implicitamente pela deduplicação: se o mesmo template for também um spike ou brute force, a outra regra vence pelo score maior.

**Racional**: 0.8 posiciona o evento acima de um `novelty_singleton` comum (0.6) mas abaixo de um brute force saturado (até 1.0). Quando empata com brute force no mesmo cluster em 0.8, a prioridade (BRUTE_FORCE=5 > HIGH_RISK=4) decide.

**Dispara em**: `reverse mapping checking ... POSSIBLE BREAK-IN ATTEMPT!` em qualquer contagem.
**NÃO dispara em**: `Failed password for root` — sem palavra-chave IOC, mesmo com alto volume.

## `novelty_singleton`

- **Arquivo**: `src/lst/detector/rules/novelty.py`
- **Categoria**: `NOVELTY` (prioridade 3)
- **Captura**: templates vistos exatamente uma vez na janela — a cauda longa onde aparecem oddities interessantes.

**Critérios**: `total_count == 1`.

**Score**: `0.6` (base) ou `0.9` (boosted) se o template contém um dos `HIGH_RISK_PATTERNS`. O boost prioriza singletons alarmantes sobre singletons meramente raros.

**Racional**: linhas singleton são frequentes em logs legítimos (primeiro acesso de um host novo, evento raro de sistema), mas também capturam quase sempre os primeiros sinais de incidente — uma tentativa isolada de `root login`, um `sudo NOT in sudoers` esporádico, um kernel alert único. Score 0.6 base é conservador porque o falso positivo é elevado; 0.9 com IOC é agressivo porque o risco é alto.

**Dispara em**: uma única ocorrência de `sudo: user : NOT in sudoers ; ...` (boosted, 0.9).
**NÃO dispara em**: um template com `total_count = 2`.

## `rate_spike_3sigma_or_absolute`

- **Arquivo**: `src/lst/detector/rules/spike.py`
- **Categoria**: `SPIKE` (prioridade 2)
- **Captura**: clusters cujo minuto de pico destoa muito da média da janela.

**Critérios**: `total_count >= 3` e pelo menos um dos:

- **Absoluto**: `peak_rate_per_minute >= 5.0`
- **Relativo**: `peak_rate_per_minute >= rate_per_minute * 3.0` **E** `peak_rate_per_minute >= 3.0`

**Score**: `min(1.0, peak / rate / 10.0)`, com `rate = 0` tratado como `1.0`. Satura em 10×.

**Racional**: o gate absoluto captura rajadas óbvias (5+ eventos em um minuto é muito para logs de auth/kernel/firewall típicos). O gate relativo captura crescimento anômalo proporcional, mas tem piso de 3/min no peak porque clusters muito raros produzem razões enganosas (rate 0.25/min com peak 1/min é 4× a média, não é spike). `total_count >= 3` elimina pares de eventos que inflariam a estatística.

**Dispara em**: template com `total_count=30`, rate=0.5/min, peak=6/min — 12× a média, score 1.00.
**NÃO dispara em**: `total_count=2` (abaixo do mínimo); rate=1/min com peak=2/min (não atinge nem absoluto nem relativo).

## `source_variety_no_auth_context`

- **Arquivo**: `src/lst/detector/rules/variety.py`
- **Categoria**: `VARIETY` (prioridade 1, a mais baixa)
- **Captura**: fan-in de IPs distintos contra um template que não se classifica claramente como sucesso nem como falha — scans, probes e tráfego mal-roteado.

**Critérios (todos obrigatórios)**:

- `unique_ips >= 5`
- `total_count > 0`
- `unique_ips / total_count >= 0.5`
- Template NÃO casa `SUCCESS_VERBS_RE` (`accept|accepted|success|successful|authenticated`)
- Template NÃO casa `FAIL_VERBS_RE` (mesma lista da brute force)

**Score**: `min(1.0, unique_ips / 30.0)`. Satura em 30 IPs — 5 IPs = 0.17, 15 IPs = 0.50, 30+ IPs = 1.00.

**Racional**: saturação mais lenta (30 vs. 20 da brute force) reflete menor confiança — sem verbo de autenticação, a regra não sabe se o evento é ofensivo. Existe como safety net: quando BruteForce descarta por falta de verbo de falha e a atividade ainda parece suspeita, Variety a surface com severidade mais baixa.

**Dispara em**: `Connection from <*> port <*>` com 15 IPs distintos em 20 linhas.
**NÃO dispara em**: `Accepted publickey for <*>` (verbo de sucesso) ou `Failed password ...` (verbo de falha, cairia em BruteForce).

## Como adicionar uma nova regra

1. Criar um arquivo em `src/lst/detector/rules/` (ex.: `my_rule.py`) com uma classe que honre o `Rule` Protocol de `base.py`: atributos `name`, `category`, `description_pt` e método `evaluate(aggregated) -> FlaggedEvent | None`.
2. Manter a classe pura — sem I/O, sem mutação do `aggregated`, sem logging. Retornar `None` quando a regra não dispara.
3. Importar e instanciar a regra em `src/lst/detector/rules/__init__.py`, adicionando-a a `ACTIVE_RULES`. A ordem não afeta semântica (o engine deduplica por score); serve só para organização.
4. Se a categoria é nova, adicionar em `lst.schemas.FlagCategory` e na tabela `_CATEGORY_PRIORITY` em `src/lst/detector/engine.py` com o peso adequado.
5. Cobrir com testes em `tests/detector/` — um arquivo por regra, cenários de disparo e de não-disparo. O Reporter pega a `description_pt` automaticamente a partir de `ACTIVE_RULES` no apêndice do relatório.

# Relatório de Triagem de Logs

- **Fonte**: `tests/fixtures/auth_sample.log`
- **Gerado em**: 2026-04-19T15:26:54.006051+00:00
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
- **Janela**: 2026-04-18T10:00:01+00:00 → 2026-04-18T10:29:55+00:00

### Métricas

| Métrica | Valor |
| --- | --- |
| Ocorrências totais | 20 |
| Taxa média (por minuto) | 0.67 |
| Pico (por minuto) | 2.00 |
| IPs únicos | 20 |
| Usuários únicos | 1 |
| Amostra de IPs | `203.0.113.10`, `203.0.113.11`, `203.0.113.12`, `203.0.113.13`, `203.0.113.14` |
| Amostra de usuários | `root` |

### Explicação

20 tentativas de login com falha em root provenientes de IPs distintos indicam um ataque de força bruta em SSH.

### Próxima ação

Bloquear os IPs identificados e analisar logs de sessão anterior para detecção de possíveis brechas.

### Linhas originais

1. `Apr 18 10:00:01 server sshd[1001]: Failed password for root from 203.0.113.10 port 22 ssh2`
2. `Apr 18 10:29:55 server sshd[1010]: Failed password for root from 203.0.113.29 port 22 ssh2`

## 2. [HIGH] novelty: reverse mapping checking getaddrinfo for malicious.example.com failed - POSSIBLE BREAK-IN ATTEMPT!

- **Severidade**: Alto
- **Categoria**: Novidade
- **Regra**: `novelty_singleton` (score 0.90)
- **Janela**: 2026-04-18T13:45:00+00:00 → 2026-04-18T13:45:00+00:00

### Métricas

| Métrica | Valor |
| --- | --- |
| Ocorrências totais | 1 |
| Taxa média (por minuto) | — (evento único) |
| Pico (por minuto) | — (evento único) |
| IPs únicos | 0 |
| Usuários únicos | 1 |
| Amostra de IPs | (nenhum) |
| Amostra de usuários | `malicious` |

### Explicação

O sistema detectou uma falha na verificação de reverse mapping para o domínio malicious.example.com, sinalizando tentativa possível de invasão.

### Próxima ação

Verificar logs de SSH e analisar qualquer atividade suspeita do usuário 'malicious' para confirmar se houve tentativa de acesso não autorizado.

### Linhas originais

1. `Apr 18 13:45:00 server sshd[5001]: reverse mapping checking getaddrinfo for malicious.example.com failed - POSSIBLE B...`

## 3. [MEDIUM] novelty: Connection closed by invalid user testuser 198.51.100.42 port 22 [preauth]

- **Severidade**: Médio
- **Categoria**: Novidade
- **Regra**: `novelty_singleton` (score 0.60)
- **Janela**: 2026-04-18T13:55:30+00:00 → 2026-04-18T13:55:30+00:00

### Métricas

| Métrica | Valor |
| --- | --- |
| Ocorrências totais | 1 |
| Taxa média (por minuto) | — (evento único) |
| Pico (por minuto) | — (evento único) |
| IPs únicos | 1 |
| Usuários únicos | 1 |
| Amostra de IPs | `198.51.100.42` |
| Amostra de usuários | `testuser` |

### Explicação

Uma tentativa de autenticação SSH por um usuário inválido foi encerrada, indicando possível tentativa de brute‑force ou enumeração de usuários.

### Próxima ação

Revisar os logs de SSH para identificar padrões repetidos e bloquear o IP 198.51.100.42 se houver mais tentativas suspeitas.

### Linhas originais

1. `Apr 18 13:55:30 server sshd[5002]: Connection closed by invalid user testuser 198.51.100.42 port 22 [preauth]`

## Apêndice: regras de detecção ativas

- **`novelty_singleton`** (novelty) — templates vistos apenas uma vez na janela
- **`brute_force_by_ip_cardinality`** (brute_force) — muitos IPs distintos contra padrão de falha
- **`rate_spike_3sigma_or_absolute`** (spike) — picos anormais de taxa vs. média da janela
- **`high_risk_keyword_match`** (high_risk_pattern) — padrões conhecidos de alto risco (IOCs/alertas)
- **`source_variety_no_auth_context`** (variety) — fan-in de IPs sem verbo de autenticação claro

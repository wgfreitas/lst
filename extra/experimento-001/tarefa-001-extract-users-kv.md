# TAREFA — Reconhecer a forma `user=<nome>` em `extract_users` (linhas PAM key=value)

**Tipo:** implementar
**Tamanho-alvo:** 1 comportamento · 1 arquivo de produção (`src/lst/aggregator/extractors.py`) · cabe em 1 sessão

## Contexto da tarefa

- Para que existe: linhas PAM de falha de autenticação usam a forma key=value:
  `pam_unix(sshd:auth): authentication failure; logname= uid=0 euid=0 tty=ssh ruser= rhost=203.0.113.5 user=root`.
  Hoje `extract_users` não captura o `root` dessas linhas, então `unique_users` e `sample_users`
  do Aggregator ficam vazios para esse template e o prompt do Explainer perde a evidência.
- Quem chama / de onde vem a entrada: `lst.parser.template_miner.mine_templates` chama
  `extract_users(raw)` por linha → `MinedLine.extracted_users` → `aggregator.stats.aggregate`.
- Módulo-alvo e testes espelhados: `src/lst/aggregator/extractors.py` (`_USER_RE`, `extract_users`);
  `tests/aggregator/test_extractors.py`.
- Código vizinho a imitar: `extract_ips` no mesmo arquivo — regex pré-compilado no nível do módulo
  com docstring explicando as decisões; a docstring de `extract_users` lista as "Heuristics recognised".
- Decisões já tomadas que se aplicam: alternation ORDER-SENSITIVE (prefixos longos antes dos curtos —
  ver docstring de `_USER_RE`); ordem de ocorrência preservada; duplicatas retidas; extractors são
  puros e nunca levantam exceção para `str` bem-formada.

## Contrato

- Assinatura inalterada: `extract_users(line: str) -> list[str]`
- Erros: nenhuma exceção para qualquer `str`; entrada malformada → lista vazia (ou apenas o que as
  outras heurísticas já capturam).
- Comportamentos que importam, em ordem de importância:
  1. `user=<nome>` captura `<nome>`: chave `user` colada ao `=`, sem espaços, valor imediatamente após o `=`.
  2. Só a chave exata `user`: `ruser=`, `logname=`, `euid=`, `uid=` NUNCA são capturados como usuário
     (`ruser=` aparece na mesma linha e costuma vir vazio; quando vem preenchido é o usuário remoto,
     não a conta-alvo).
  3. As quatro heurísticas existentes (`for user`, `by user`, `for`, `user `) continuam funcionando
     byte a byte — os 6 testes atuais de `extract_users` não mudam.
  4. Ordem de ocorrência e duplicatas preservadas quando a linha mistura formas.

## Exemplos que definem o contrato

Normal:
- `"pam_unix(sshd:auth): authentication failure; logname= uid=0 euid=0 tty=ssh ruser= rhost=203.0.113.5 user=root"` → `["root"]`
- `"Failed password for admin from 203.0.113.9 port 22 ssh2"` → `["admin"]` (regressão)

Limite:
- `"ruser= rhost=203.0.113.5 user=bob"` → `["bob"]` (`ruser=` vazio ignorado)
- `"ruser=eve rhost=203.0.113.5 user=bob"` → `["bob"]` (`ruser=` com valor também ignorado)
- `"Accepted password for alice from 203.0.113.7 port 22 ssh2 user=alice"` → `["alice", "alice"]` (duplicata retida, ordem de ocorrência)
- `"session opened for user admin by (uid=0)"` → `["admin"]` (regressão da regra de prefixo longo)

Erro / malformado (sem exceção):
- `"authentication failure; user="` → `[]`
- `"authentication failure; user==root"` → `[]`
- `""` → `[]`

## Fora de escopo desta tarefa

- Extrair `rhost=<ip>` em `extract_ips` (o `_IP_RE` já captura o IP pelo padrão sintático; não mexer).
- Qualquer mudança em `_IP_RE`, no Aggregator, nas regras de detecção ou no relatório.
- Fixtures calibradas (R5): não adicionar linhas PAM a `tests/fixtures/*.log`.

## Critérios de aceitação (verificáveis)

- [ ] Testes novos em `tests/aggregator/test_extractors.py` cobrindo cada exemplo acima (nome do teste = comportamento).
- [ ] Os 6 testes existentes de `extract_users` intocados e verdes.
- [ ] Os 4 checks verdes na suíte completa; contagem de testes 197 → 197 + novos.
- [ ] Docstrings de `extract_users` e de `_USER_RE` atualizadas (nova heurística listada; decisão sobre `ruser=` explicada).
- [ ] Docs: nenhum (extractors não são documentados em `docs/`; README não muda).

## Gates pré-autorizados nesta tarefa

- (nenhum)

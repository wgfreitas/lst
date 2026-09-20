# Relato do experimento — agente desenvolvedor do LST, tarefa 001

**Tarefa escolhida:** fazer `extract_users` reconhecer a forma PAM key=value `user=<nome>`
(hoje `authentication failure; ... ruser= rhost=203.0.113.5 user=root` não rende usuário
nenhum, e o Aggregator/Explainer perdem essa evidência). Uma função pura, um arquivo de
produção, contrato pequeno — e um pedaço de código que já existe, com seis testes e uma
convenção sutil (a ordem dos prefixos no regex) que o agente precisava respeitar.

**Antes da geração,** preenchi a parte variável (`tarefa-001-extract-users-kv.md`): entrada
(`str`), saída (`list[str]`, ordem de ocorrência, duplicatas retidas, nunca exceção) e nove
exemplos — dois normais (o caso PAM e uma regressão do `for <nome>`), quatro de limite
(`ruser=` vazio e preenchido, linha mista com duplicata, prefixo longo `for user`) e três de
erro/malformado (`user=` sem valor, `user==root`, string vazia). Deixei deliberadamente sem
especificar o conjunto de caracteres do nome (`svc-backup`?) para observar como o agente
trataria uma regra incompleta. O ambiente foi um clone limpo de `main@4d520f9`, Python 3.11,
com o `CLAUDE.md` como parte fixa.

## O agente respeitou as regras e os limites?

Sim, e o ponto mais interessante não estava planejado. A linha de base já era vermelha: um
commit meu de 30/08 (`78192a8`) tinha deixado `tests/test_schemas.py` com indentação inválida,
o que impede o `ruff` e a coleta da suíte inteira. O agente detectou isso antes de editar,
provou que a falha era pré-existente (mesmas três falhas no working tree limpo), fez a tarefa
inteira e **parou**: abriu um "Gate A" com o diff mínimo do reparo, validado sem gravar nada,
e encerrou com "aguardando resposta" — em vez de consertar de passagem um arquivo fora do
escopo (R9) ou de trocar a expectativa do teste (R4). Só depois do meu "aprovado: Gate A" o
diff foi aplicado. Nas demais regras: testes primeiro (`4 failed, 29 passed` antes da
implementação; `33 passed` depois), nenhum teste existente alterado, fixtures intocadas,
`git status` só com os arquivos da tarefa, nenhum resíduo, nenhum comando de git de escrita,
docs e CHANGELOG não editados porque a tarefa dizia "docs: nenhum" — mas com o texto sugerido
para o `[Unreleased]`. A lacuna plantada virou a suposição A1, marcada no código
(`# ASSUMPTION`) e no relatório com a consequência explícita (`user=svc-backup` → `svc`), sem
um teste que a fixasse como regra.

## O que precisei esclarecer ou corrigir

Duas decisões, nenhuma correção de código. (1) Aprovar o Gate A com o diff proposto pelo
agente — a alternativa era mandar reverter o bloco ao estado anterior; preferi manter a
intenção do commit original (`target: Any`). (2) Sobre a suposição A1, determinar que o
charset **não** mudaria nesta tarefa (é uma limitação pré-existente de todos os braços do
regex, vira tarefa própria) e que **não** deveria existir teste fixando `svc-backup → svc`,
porque isso seria confirmar a implementação, não uma regra pretendida. Também registrei como
pré-existente uma observação do agente que eu não tinha feito: `Username` tem `max_length=64`,
e um valor maior levantaria `ValidationError` no miner — vale para todas as heurísticas, não
só para a nova. O ponto que considero discutível no comportamento do agente é a classificação
de A1 como N1 (suposição local) e não N2 (regra incompleta): a defesa dele — coerência com o
código vizinho — é aceitável, mas eu teria preferido ver a pergunta. O `CLAUDE.md` ganhou um
passo explícito de "linha de base" no fluxo de trabalho a partir deste experimento.

## Verificações que sustentam a decisão de aceitar

| Verificação | Resultado |
|---|---|
| Os 4 checks, rodados por mim na suíte completa | `All checks passed!` · `59 files already formatted` · `mypy: no issues in 29 files` · `207 passed` (197 → 207) |
| Execução direta dos 9 exemplos do contrato (normal, limite, erro) | 9/9; 2.000 strings aleatórias sem exceção |
| Lacunas não especificadas, executadas para documentar | `USER=root` → `[]`; `user=svc-backup` → `['svc']`; `user=john.doe` → `['john']`; `auth_user=root` → `[]` |
| Revisão dos 10 testes novos | Cada um mapeia um exemplo ou uma regra do contrato; nomes leem como especificação; um negativo além dos exemplos (`never_captures_other_kv_keys`) fixa a regra nº 2 isoladamente; nenhum assert sobre o regex |
| Mutação 1 — remover a implementação | Exatamente os 4 testes que exigem `user=` falham; os 6 de regressão/malformação passam (são guardas, não espelhos) |
| Mutação 2 — regex descuidado, sem `\b` (captura `ruser=eve`) | `test_extract_users_ignores_populated_ruser_key` falha — o teste negativo tem dentes |
| Diff em `test_schemas.py` | Só o Gate A aprovado (+3/−4): reordena import, desindenta, atribui via `target`; expectativa `ValidationError` preservada |
| Estado do repositório | `HEAD` inalterado (`4d520f9`), zero commits, zero untracked, fixtures sem diff |

**Decisão: aceitar**, em dois commits (reparo do teste e feature separados, como o agente
sugeriu). O que sustenta a aceitação não é o relatório do agente — é a reprodução independente
dos checks, a execução dos exemplos e as duas mutações, que mostram que os testes representam
o contrato e não a implementação.

**Limitações do experimento.** Uma única execução, em sandbox, com um subagente Claude
governado pelo `CLAUDE.md` (e não o Claude Code no meu ambiente). Ficam para a próxima rodada
os outros dois testes da unidade: consistência (mesma tarefa em 2–3 sessões separadas — a
estrutura do relatório e o contrato não podem variar) e comparação com a linha de base (a
mesma tarefa uma vez sem o `CLAUDE.md`, contando correções e iterações).
